from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit
import json
import os
import re
import time
import shutil
import subprocess
import tarfile
import uuid
import zipfile


class IntakeError(RuntimeError):
    """Actionable intake failure with a stable machine-readable code."""

    def __init__(self, message: str, code: str = "INTAKE_FAILED") -> None:
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"error": type(self).__name__, "code": self.code, "message": str(self)}


class IntakeKind(str, Enum):
    DIRECTORY = "directory"
    ARCHIVE = "archive"
    FILES = "files"
    PASTE = "paste"
    GIT = "git"
    NEW = "new"


@dataclass(slots=True)
class IntakeItem:
    relative_path: str
    size: int = 0


@dataclass(slots=True)
class IntakeRequest:
    kind: IntakeKind
    objective: str = ""
    source_path: str | None = None
    git_url: str | None = None
    pasted_items: list[dict[str, str]] = field(default_factory=list)
    display_name: str | None = None


@dataclass(slots=True)
class IntakeResult:
    root: Path
    source: Path | str
    extracted_files: int = 0
    kind: IntakeKind = IntakeKind.DIRECTORY
    managed: bool = False
    detected_root: Path | None = None
    warnings: list[str] = field(default_factory=list)
    bytes_materialized: int = 0

    def __post_init__(self) -> None:
        if self.detected_root is None:
            self.detected_root = self.root


_ARCHIVE_SUFFIXES = (
    ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz",
)
_PROJECT_MARKERS = (
    ".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "CMakeLists.txt",
    "setup.py", "package.xml", "README.md", "README.rst", "README.txt", "src",
)
_METADATA_DIRS = {"__MACOSX", ".DS_Store"}


def _slug(value: str | None, fallback: str = "project") -> str:
    text = (value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    return (text or fallback)[:64]


def _archive_kind(path: Path) -> str | None:
    name = path.name.lower()
    for suffix in _ARCHIVE_SUFFIXES:
        if name.endswith(suffix):
            return suffix
    return None


def _safe_relative(value: str, *, code: str, label: str) -> Path:
    normalized = str(value).replace("\\", "/")
    pure = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or pure.is_absolute() or ".." in pure.parts:
        raise IntakeError(f"unsafe {label}: {value}", code)
    if pure.parts and re.match(r"^[A-Za-z]:$", pure.parts[0]):
        raise IntakeError(f"unsafe {label}: {value}", code)
    cleaned = Path(*[part for part in pure.parts if part not in {"", "."}])
    if not cleaned.parts:
        raise IntakeError(f"unsafe {label}: {value}", code)
    return cleaned


def _contained(root: Path, relative: Path, *, code: str, label: str) -> Path:
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise IntakeError(f"unsafe {label}: {relative}", code) from exc
    return target


def _score_root(path: Path) -> int:
    score = 0
    for marker in _PROJECT_MARKERS:
        candidate = path / marker
        if candidate.exists():
            score += 5 if marker in {".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "CMakeLists.txt", "package.xml"} else 2
    return score


def _detect_root(destination: Path) -> Path:
    children = [p for p in destination.iterdir() if p.name not in _METADATA_DIRS]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    candidates = [p for p in children if p.is_dir()]
    scored = sorted(((_score_root(p), p) for p in candidates), key=lambda pair: pair[0], reverse=True)
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] >= scored[1][0] + 5):
        return scored[0][1]
    return destination


def _check_limits(file_count: int, total_bytes: int, max_files: int, max_bytes: int, *, archive_name: str) -> None:
    if file_count > max_files:
        raise IntakeError(f"{archive_name} contains too many files: {file_count} > {max_files}", "LIMIT_EXCEEDED")
    if total_bytes > max_bytes:
        raise IntakeError(f"{archive_name} uncompressed size exceeds limit: {total_bytes} > {max_bytes}", "LIMIT_EXCEEDED")


def _extract_zip(archive: Path, destination: Path, max_files: int, max_bytes: int) -> tuple[int, int]:
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            files = [m for m in members if not m.is_dir()]
            total = sum(max(0, int(m.file_size)) for m in files)
            _check_limits(len(files), total, max_files, max_bytes, archive_name="zip")
            planned: list[tuple[zipfile.ZipInfo, Path]] = []
            for member in members:
                rel = _safe_relative(member.filename, code="ARCHIVE_UNSAFE", label="zip member")
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise IntakeError(f"unsafe zip symlink member: {member.filename}", "ARCHIVE_UNSAFE")
                if mode not in {0, 0o040000, 0o100000}:
                    raise IntakeError(f"unsafe zip special member: {member.filename}", "ARCHIVE_UNSAFE")
                target = _contained(destination, rel, code="ARCHIVE_UNSAFE", label="zip member")
                planned.append((member, target))
            extracted = 0
            for member, target in planned:
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                extracted += 1
            return extracted, total
    except IntakeError:
        raise
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise IntakeError(f"invalid zip archive: {archive}", "ARCHIVE_CORRUPT") from exc


def _extract_tar(archive: Path, destination: Path, max_files: int, max_bytes: int) -> tuple[int, int]:
    try:
        with tarfile.open(archive, "r:*") as tf:
            members = tf.getmembers()
            regular = [m for m in members if m.isfile()]
            total = sum(max(0, int(m.size)) for m in regular)
            _check_limits(len(regular), total, max_files, max_bytes, archive_name="tar")
            planned: list[tuple[tarfile.TarInfo, Path]] = []
            for member in members:
                rel = _safe_relative(member.name, code="ARCHIVE_UNSAFE", label="tar member")
                if not (member.isdir() or member.isfile()):
                    raise IntakeError(f"unsafe tar special/link member: {member.name}", "ARCHIVE_UNSAFE")
                target = _contained(destination, rel, code="ARCHIVE_UNSAFE", label="tar member")
                planned.append((member, target))
            extracted = 0
            for member, target in planned:
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                if src is None:
                    raise IntakeError(f"could not read tar member: {member.name}", "ARCHIVE_CORRUPT")
                with src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                extracted += 1
            return extracted, total
    except IntakeError:
        raise
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise IntakeError(f"invalid tar archive: {archive}", "ARCHIVE_CORRUPT") from exc


def _sanitize_git_url(url: str) -> str:
    value = str(url).strip()
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-git-url>"
    if parts.scheme and parts.netloc:
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        return urlunsplit((parts.scheme, host + port, parts.path, parts.query, parts.fragment))
    return value


class ProjectIntake:
    """Backward-compatible directory/ZIP intake facade."""

    def __init__(self, max_files: int = 100_000, max_uncompressed_bytes: int = 8 * 1024 * 1024 * 1024):
        if max_files < 1 or max_uncompressed_bytes < 1:
            raise ValueError("intake limits must be positive")
        self.max_files = max_files
        self.max_uncompressed_bytes = max_uncompressed_bytes

    def from_directory(self, source: str | Path) -> IntakeResult:
        root = Path(source).expanduser().resolve()
        if not root.is_dir():
            raise IntakeError(f"project directory does not exist: {root}", "SOURCE_NOT_FOUND")
        return IntakeResult(root=root, source=root, extracted_files=0, kind=IntakeKind.DIRECTORY, managed=False)

    def from_zip(self, archive: str | Path, destination: str | Path) -> IntakeResult:
        archive_path = Path(archive).expanduser().resolve()
        dest = Path(destination).expanduser().resolve()
        if not archive_path.is_file():
            raise IntakeError(f"zip archive does not exist: {archive_path}", "SOURCE_NOT_FOUND")
        if dest.exists() and any(dest.iterdir()):
            raise IntakeError(f"destination is not empty: {dest}", "WORKSPACE_CREATE_FAILED")
        dest.mkdir(parents=True, exist_ok=True)
        try:
            extracted, total = _extract_zip(archive_path, dest, self.max_files, self.max_uncompressed_bytes)
        except Exception:
            if dest.exists() and not any(dest.iterdir()):
                dest.rmdir()
            raise
        root = _detect_root(dest)
        return IntakeResult(root=root, source=archive_path, extracted_files=extracted, kind=IntakeKind.ARCHIVE, managed=False, bytes_materialized=total)


class UniversalIntakeService:
    """Normalize common project sources into a concrete local directory."""

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        staging_root: str | Path | None = None,
        max_files: int = 100_000,
        max_uncompressed_bytes: int = 8 * 1024 * 1024 * 1024,
    ) -> None:
        if max_files < 1 or max_uncompressed_bytes < 1:
            raise ValueError("intake limits must be positive")
        home = Path.home() / ".engineering-office"
        self.workspace_root = Path(workspace_root or home / "workspaces").expanduser().resolve()
        self.staging_root = Path(staging_root or home / "staging").expanduser().resolve()
        self.max_files = max_files
        self.max_uncompressed_bytes = max_uncompressed_bytes
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)

    def _workspace(self, name: str | None) -> Path:
        base = _slug(name)
        for _ in range(50):
            path = self.workspace_root / f"{base}-{uuid.uuid4().hex[:8]}"
            try:
                path.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                continue
            return path
        raise IntakeError("could not allocate a unique managed workspace", "WORKSPACE_CREATE_FAILED")

    def _record(self, result: IntakeResult, objective: str = "") -> IntakeResult:
        if not result.managed:
            return result
        office = result.root / ".office"
        office.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": result.kind.value,
            "source": _sanitize_git_url(str(result.source)) if result.kind is IntakeKind.GIT else str(result.source),
            "managed": result.managed,
            "extracted_files": result.extracted_files,
            "bytes_materialized": result.bytes_materialized,
            "detected_root": str(result.detected_root or result.root),
            "warnings": result.warnings,
            "objective_present": bool(objective.strip()),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (office / "intake.json").write_text(json.dumps(payload, indent=2, sort_keys=True))
        return result

    def from_path(
        self,
        source: str | Path,
        objective: str = "",
        display_name: str | None = None,
        *,
        treat_as_archive: bool = False,
    ) -> IntakeResult:
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise IntakeError(f"source does not exist: {path}", "SOURCE_NOT_FOUND")
        if path.is_dir():
            return IntakeResult(root=path, source=path, kind=IntakeKind.DIRECTORY, managed=False)
        kind = _archive_kind(path)
        if kind:
            return self.from_archive(path, objective=objective, display_name=display_name)
        if treat_as_archive:
            raise IntakeError(f"unsupported archive format: {path.name}", "UNSUPPORTED_ARCHIVE")
        if path.is_file():
            return self.from_files([path], objective=objective, display_name=display_name or path.stem)
        raise IntakeError(f"unsupported source: {path}", "SOURCE_NOT_FOUND")

    def from_archive(self, archive: str | Path, objective: str = "", display_name: str | None = None) -> IntakeResult:
        archive_path = Path(archive).expanduser().resolve()
        if not archive_path.is_file():
            raise IntakeError(f"archive does not exist: {archive_path}", "SOURCE_NOT_FOUND")
        suffix = _archive_kind(archive_path)
        if suffix is None:
            raise IntakeError(f"unsupported archive format: {archive_path.name}", "UNSUPPORTED_ARCHIVE")
        workspace = self._workspace(display_name or archive_path.name.split(".")[0])
        try:
            if suffix == ".zip":
                count, total = _extract_zip(archive_path, workspace, self.max_files, self.max_uncompressed_bytes)
            else:
                count, total = _extract_tar(archive_path, workspace, self.max_files, self.max_uncompressed_bytes)
            root = _detect_root(workspace)
            result = IntakeResult(
                root=root, source=archive_path, extracted_files=count, kind=IntakeKind.ARCHIVE,
                managed=True, detected_root=root, bytes_materialized=total,
            )
            return self._record(result, objective)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def from_files(self, files: list[str | Path], objective: str = "", display_name: str | None = None) -> IntakeResult:
        if not files:
            raise IntakeError("no files were provided", "UPLOAD_INCOMPLETE")
        if len(files) > self.max_files:
            raise IntakeError(f"too many files: {len(files)} > {self.max_files}", "LIMIT_EXCEEDED")
        resolved: list[Path] = []
        total = 0
        for item in files:
            path = Path(item).expanduser().resolve()
            if not path.is_file():
                raise IntakeError(f"source file does not exist: {path}", "SOURCE_NOT_FOUND")
            total += path.stat().st_size
            resolved.append(path)
        if total > self.max_uncompressed_bytes:
            raise IntakeError(f"uploaded files exceed byte limit: {total} > {self.max_uncompressed_bytes}", "LIMIT_EXCEEDED")
        workspace = self._workspace(display_name or resolved[0].stem)
        try:
            seen: set[str] = set()
            for path in resolved:
                if path.name in seen:
                    raise IntakeError(f"duplicate uploaded filename: {path.name}", "UPLOAD_INVALID_PATH")
                seen.add(path.name)
                shutil.copy2(path, workspace / path.name)
            result = IntakeResult(workspace, "local-files", len(resolved), IntakeKind.FILES, True, workspace, [], total)
            return self._record(result, objective)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def from_paste(self, name: str | None, objective: str, items: list[dict[str, str]]) -> IntakeResult:
        if not items:
            raise IntakeError("paste intake requires at least one item", "UPLOAD_INCOMPLETE")
        if len(items) > self.max_files:
            raise IntakeError(f"too many pasted items: {len(items)} > {self.max_files}", "LIMIT_EXCEEDED")
        prepared: list[tuple[Path, bytes]] = []
        total = 0
        seen: set[str] = set()
        for index, item in enumerate(items, start=1):
            raw_path = str(item.get("path", "")).strip() or ("PASTED_INPUT.txt" if index == 1 else f"PASTED_INPUT_{index}.txt")
            rel = _safe_relative(raw_path, code="UPLOAD_INVALID_PATH", label="pasted filename")
            key = rel.as_posix()
            if key in seen:
                raise IntakeError(f"duplicate pasted filename: {key}", "UPLOAD_INVALID_PATH")
            seen.add(key)
            data = str(item.get("content", "")).encode()
            total += len(data)
            if total > self.max_uncompressed_bytes:
                raise IntakeError(f"pasted content exceeds byte limit: {total} > {self.max_uncompressed_bytes}", "LIMIT_EXCEEDED")
            prepared.append((rel, data))
        workspace = self._workspace(name or "pasted-project")
        try:
            for rel, data in prepared:
                target = _contained(workspace, rel, code="UPLOAD_INVALID_PATH", label="pasted filename")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            result = IntakeResult(workspace, "paste", len(prepared), IntakeKind.PASTE, True, workspace, [], total)
            return self._record(result, objective)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def from_new(self, name: str | None, objective: str) -> IntakeResult:
        if not objective.strip():
            raise IntakeError("new projects require an objective", "OBJECTIVE_REQUIRED")
        workspace = self._workspace(name or "new-project")
        try:
            title = (name or "New Engineering Project").strip()
            created = datetime.now(timezone.utc).isoformat()
            brief = f"# {title}\n\n## Objective\n\n{objective.strip()}\n\nCreated: {created}\n"
            (workspace / "PROJECT_BRIEF.md").write_text(brief)
            result = IntakeResult(workspace, "new-project", 1, IntakeKind.NEW, True, workspace, [], len(brief.encode()))
            return self._record(result, objective)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def from_tree(self, source_dir: str | Path, objective: str = "", display_name: str | None = None) -> IntakeResult:
        source = Path(source_dir).expanduser().resolve()
        if not source.is_dir():
            raise IntakeError(f"uploaded staging directory does not exist: {source}", "UPLOAD_INCOMPLETE")
        files = [p for p in source.rglob("*") if p.is_file()]
        if not files:
            raise IntakeError("upload session contains no files", "UPLOAD_INCOMPLETE")
        if len(files) > self.max_files:
            raise IntakeError(f"too many uploaded files: {len(files)} > {self.max_files}", "LIMIT_EXCEEDED")
        total = 0
        for item in files:
            if item.is_symlink():
                raise IntakeError(f"uploaded symlinks are not allowed: {item.name}", "UPLOAD_INVALID_PATH")
            total += item.stat().st_size
        if total > self.max_uncompressed_bytes:
            raise IntakeError(f"uploaded files exceed byte limit: {total} > {self.max_uncompressed_bytes}", "LIMIT_EXCEEDED")
        workspace = self._workspace(display_name or source.name)
        try:
            for item in files:
                rel = item.relative_to(source)
                target = _contained(workspace, rel, code="UPLOAD_INVALID_PATH", label="uploaded path")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
            root = _detect_root(workspace)
            result = IntakeResult(root, "browser-upload", len(files), IntakeKind.FILES, True, root, [], total)
            return self._record(result, objective)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def from_git(self, url: str, name: str | None = None, objective: str = "") -> IntakeResult:
        value = str(url).strip()
        if not value:
            raise IntakeError("Git repository URL is required", "GIT_CLONE_FAILED")
        if shutil.which("git") is None:
            raise IntakeError("git executable is not available", "GIT_NOT_AVAILABLE")
        sanitized = _sanitize_git_url(value)
        workspace = self._workspace(name or Path(urlsplit(value).path).stem or "git-project")
        try:
            proc = subprocess.run(
                ["git", "clone", "--quiet", value, str(workspace)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
                shell=False,
            )
            if proc.returncode != 0:
                raise IntakeError(f"could not clone Git repository: {sanitized}", "GIT_CLONE_FAILED")
            count = sum(1 for p in workspace.rglob("*") if p.is_file() and ".git" not in p.parts)
            total = sum(p.stat().st_size for p in workspace.rglob("*") if p.is_file() and ".git" not in p.parts)
            _check_limits(count, total, self.max_files, self.max_uncompressed_bytes, archive_name="git repository")
            result = IntakeResult(workspace, sanitized, count, IntakeKind.GIT, True, workspace, [], total)
            return self._record(result, objective)
        except subprocess.TimeoutExpired as exc:
            raise IntakeError(f"Git clone timed out: {sanitized}", "GIT_CLONE_FAILED") from exc
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise


class IntakeSessionManager:
    """Stream browser uploads into bounded staging sessions before commit."""

    def __init__(self, service: UniversalIntakeService, session_ttl_seconds: int = 24 * 60 * 60) -> None:
        if session_ttl_seconds < 1:
            raise ValueError("session TTL must be positive")
        self.service = service
        self.session_ttl_seconds = int(session_ttl_seconds)
        self._sessions: dict[str, dict[str, object]] = {}
        self.cleanup_stale()

    def create(self, display_name: str | None = None, objective: str = "", mode: str = "files") -> dict[str, object]:
        self.cleanup_stale()
        if mode not in {"files", "archive"}:
            raise IntakeError(f"unsupported upload session mode: {mode}", "UPLOAD_INCOMPLETE")
        session_id = uuid.uuid4().hex[:16]
        root = self.service.staging_root / f"session-{session_id}"
        (root / "files").mkdir(parents=True, exist_ok=False)
        row: dict[str, object] = {
            "session_id": session_id,
            "staging_dir": str(root),
            "created_at": time.time(),
            "display_name": display_name,
            "objective": objective,
            "mode": mode,
            "files": set(),
            "total_bytes": 0,
        }
        self._sessions[session_id] = row
        return {k: v for k, v in row.items() if k != "files"}

    def _get(self, session_id: str) -> dict[str, object]:
        row = self._sessions.get(str(session_id))
        if row is None:
            raise IntakeError(f"upload session is missing or expired: {session_id}", "UPLOAD_INCOMPLETE")
        return row

    def upload(self, session_id: str, relative_path: str, data, size: int | None = None) -> dict[str, object]:
        row = self._get(session_id)
        rel = _safe_relative(relative_path, code="UPLOAD_INVALID_PATH", label="upload path")
        key = rel.as_posix()
        files = row["files"]
        assert isinstance(files, set)
        if key in files:
            raise IntakeError(f"duplicate upload path: {key}", "UPLOAD_INVALID_PATH")
        if len(files) + 1 > self.service.max_files:
            raise IntakeError(f"upload exceeds file limit: {self.service.max_files}", "LIMIT_EXCEEDED")
        existing_total = int(row["total_bytes"])
        if size is not None and (size < 0 or existing_total + size > self.service.max_uncompressed_bytes):
            raise IntakeError(f"upload exceeds byte limit: {self.service.max_uncompressed_bytes}", "LIMIT_EXCEEDED")
        staging = Path(str(row["staging_dir"]))
        target = _contained(staging / "files", rel, code="UPLOAD_INVALID_PATH", label="upload path")
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = data if hasattr(data, "read") else None
        if stream is None:
            payload = bytes(data)
            stream = __import__("io").BytesIO(payload)
        written = 0
        remaining = size
        try:
            with target.open("xb") as out:
                while remaining is None or remaining > 0:
                    want = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
                    chunk = stream.read(want)
                    if not chunk:
                        break
                    written += len(chunk)
                    if remaining is not None:
                        remaining -= len(chunk)
                    if existing_total + written > self.service.max_uncompressed_bytes:
                        raise IntakeError(f"upload exceeds byte limit: {self.service.max_uncompressed_bytes}", "LIMIT_EXCEEDED")
                    out.write(chunk)
            if size is not None and written != size:
                raise IntakeError(f"upload size mismatch for {key}: expected {size}, received {written}", "UPLOAD_INCOMPLETE")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        files.add(key)
        row["total_bytes"] = existing_total + written
        os.utime(staging, None)
        return {"session_id": session_id, "path": key, "size": written, "files": len(files), "total_bytes": row["total_bytes"]}

    def commit(self, session_id: str) -> IntakeResult:
        row = self._get(session_id)
        files = row["files"]
        assert isinstance(files, set)
        if not files:
            raise IntakeError("upload session contains no files", "UPLOAD_INCOMPLETE")
        staging = Path(str(row["staging_dir"]))
        try:
            if str(row.get("mode") or "files") == "archive":
                if len(files) != 1:
                    raise IntakeError("archive upload requires exactly one file", "UPLOAD_INCOMPLETE")
                only = next(iter(files))
                return self.service.from_archive(
                    staging / "files" / Path(only),
                    objective=str(row.get("objective") or ""),
                    display_name=str(row.get("display_name") or "") or None,
                )
            return self.service.from_tree(
                staging / "files",
                objective=str(row.get("objective") or ""),
                display_name=str(row.get("display_name") or "") or None,
            )
        finally:
            self.cancel(session_id)

    def cancel(self, session_id: str) -> dict[str, object]:
        row = self._sessions.pop(str(session_id), None)
        if row is None:
            return {"session_id": str(session_id), "cancelled": False}
        shutil.rmtree(Path(str(row["staging_dir"])), ignore_errors=True)
        return {"session_id": str(session_id), "cancelled": True}

    def cleanup_stale(self, now: float | None = None) -> list[str]:
        current = time.time() if now is None else float(now)
        removed: list[str] = []
        for path in self.service.staging_root.glob("session-*"):
            try:
                stale = current - path.stat().st_mtime > self.session_ttl_seconds
            except FileNotFoundError:
                continue
            if not stale:
                continue
            session_id = path.name.removeprefix("session-")
            shutil.rmtree(path, ignore_errors=True)
            self._sessions.pop(session_id, None)
            removed.append(session_id)
        return removed
