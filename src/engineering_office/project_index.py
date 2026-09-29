from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import sqlite3


_DEFAULT_EXCLUDES = {".git", ".office", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "node_modules"}


@dataclass(slots=True)
class IndexUpdate:
    generation: int
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    rebuilt: bool = False


@dataclass(slots=True)
class IndexGeneration:
    generation: int
    file_count: int
    changed_count: int
    removed_count: int


class ProjectIndex:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.index_dir = self.root / ".office" / "index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.index_dir / "index.db"
        self.generation_path = self.index_dir / "generation.json"
        self.manifest_path = self.index_dir / "manifest.json"
        self._last_update: IndexUpdate | None = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,sha256 TEXT NOT NULL,file_class TEXT,language TEXT,module TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        conn.commit()
        return conn

    def _reset_corrupt(self) -> None:
        for suffix in ["", "-wal", "-shm"]:
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    @staticmethod
    def _hash(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _iter_files(self) -> tuple[list[Path], list[str]]:
        files: list[Path] = []
        excluded: list[str] = []
        for base, dirs, names in os.walk(self.root):
            base_path = Path(base)
            rel_base = base_path.relative_to(self.root)
            kept_dirs = []
            for name in dirs:
                rel = (rel_base / name).as_posix()
                if name in _DEFAULT_EXCLUDES:
                    excluded.append(rel)
                else:
                    kept_dirs.append(name)
            dirs[:] = kept_dirs
            for name in names:
                path = base_path / name
                rel = path.relative_to(self.root).as_posix()
                if any(part in _DEFAULT_EXCLUDES for part in Path(rel).parts):
                    excluded.append(rel)
                    continue
                if path.is_symlink() or not path.is_file():
                    excluded.append(rel)
                    continue
                files.append(path)
        return sorted(files, key=lambda p: p.relative_to(self.root).as_posix()), sorted(set(excluded))

    @staticmethod
    def _classify(path: Path) -> tuple[str, str]:
        suffix = path.suffix.lower()
        language = {
            ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
            ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "c-cpp-header", ".hpp": "cpp-header",
            ".rs": "rust", ".go": "go", ".java": "java", ".sh": "shell", ".yaml": "yaml", ".yml": "yaml",
            ".json": "json", ".xml": "xml", ".xacro": "xacro", ".sdf": "sdf", ".urdf": "urdf", ".md": "markdown",
        }.get(suffix, "unknown")
        file_class = "source" if language in {"python","javascript","typescript","cpp","c","c-cpp-header","cpp-header","rust","go","java","shell"} else "config" if language in {"yaml","json","xml","xacro","sdf","urdf"} else "documentation" if language == "markdown" else "asset"
        return file_class, language

    def update(self) -> IndexUpdate:
        rebuilt = False
        try:
            conn = self._connect()
            existing = {row[0]: {"size": row[1], "mtime_ns": row[2], "sha256": row[3]} for row in conn.execute("SELECT path,size,mtime_ns,sha256 FROM files")}
            row = conn.execute("SELECT value FROM meta WHERE key='generation'").fetchone()
            generation = int(row[0]) + 1 if row else 1
        except sqlite3.DatabaseError:
            self._reset_corrupt()
            rebuilt = True
            conn = self._connect()
            existing = {}
            generation = 1

        files, excluded = self._iter_files()
        current: dict[str, tuple[int,int,str,str,str]] = {}
        changed: list[str] = []
        unchanged: list[str] = []
        for path in files:
            rel = path.relative_to(self.root).as_posix()
            stat = path.stat()
            digest = self._hash(path)
            file_class, language = self._classify(path)
            current[rel] = (stat.st_size, stat.st_mtime_ns, digest, file_class, language)
            old = existing.get(rel)
            if old is not None and old["sha256"] == digest:
                unchanged.append(rel)
            else:
                changed.append(rel)
            conn.execute(
                "INSERT INTO files(path,size,mtime_ns,sha256,file_class,language,module) VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET size=excluded.size,mtime_ns=excluded.mtime_ns,sha256=excluded.sha256,file_class=excluded.file_class,language=excluded.language,module=excluded.module",
                (rel, stat.st_size, stat.st_mtime_ns, digest, file_class, language, None),
            )
        removed = sorted(set(existing) - set(current))
        for rel in removed:
            conn.execute("DELETE FROM files WHERE path=?", (rel,))
        conn.execute("INSERT INTO meta(key,value) VALUES('generation',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(generation),))
        conn.commit(); conn.close()

        update = IndexUpdate(generation=generation, changed=sorted(changed), unchanged=sorted(unchanged), removed=removed, excluded=excluded, rebuilt=rebuilt)
        self._last_update = update
        self.generation_path.write_text(json.dumps({"generation": generation, "changed": update.changed, "unchanged": update.unchanged, "removed": update.removed, "excluded": update.excluded}, indent=2), encoding="utf-8")
        self.manifest_path.write_text(json.dumps({"schema": 1, "file_count": len(current), "generation": generation}, indent=2), encoding="utf-8")
        return update

    def status(self) -> dict[str, Any]:
        try:
            conn = self._connect()
            row = conn.execute("SELECT value FROM meta WHERE key='generation'").fetchone()
            file_count = int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])
            conn.close()
            generation = int(row[0]) if row else 0
        except sqlite3.DatabaseError:
            generation = 0; file_count = 0
        latest = self._last_update
        if latest is None and self.generation_path.is_file():
            try:
                raw = json.loads(self.generation_path.read_text())
                latest = IndexUpdate(generation=int(raw.get("generation", generation)), changed=list(raw.get("changed", [])), unchanged=list(raw.get("unchanged", [])), removed=list(raw.get("removed", [])), excluded=list(raw.get("excluded", [])))
            except Exception:
                latest = None
        return {
            "generation": generation,
            "file_count": file_count,
            "changed_count": len(latest.changed) if latest else 0,
            "unchanged_count": len(latest.unchanged) if latest else 0,
            "removed_count": len(latest.removed) if latest else 0,
            "excluded_count": len(latest.excluded) if latest else 0,
            "changed": list(latest.changed) if latest else [],
            "removed": list(latest.removed) if latest else [],
        }

    def records(self) -> list[dict[str, Any]]:
        try:
            conn = self._connect()
            rows = [dict(path=r[0], size=r[1], mtime_ns=r[2], sha256=r[3], file_class=r[4], language=r[5], module=r[6]) for r in conn.execute("SELECT path,size,mtime_ns,sha256,file_class,language,module FROM files ORDER BY path")]
            conn.close(); return rows
        except sqlite3.DatabaseError:
            return []


class IncrementalAnalysisCache:
    def __init__(self, project_root: str | Path):
        root = Path(project_root).resolve()
        self.path = root / ".office" / "index" / "analysis-cache.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        conn = self._connect()
        conn.execute("CREATE TABLE IF NOT EXISTS cache(file_hash TEXT NOT NULL,schema_version TEXT NOT NULL,model_family TEXT NOT NULL,prompt_contract_version TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(file_hash,schema_version,model_family,prompt_contract_version))")
        conn.commit(); conn.close()

    def get(self, file_hash: str, schema_version: str, model_family: str, prompt_contract_version: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute("SELECT data FROM cache WHERE file_hash=? AND schema_version=? AND model_family=? AND prompt_contract_version=?", (file_hash, schema_version, model_family, prompt_contract_version)).fetchone()
        conn.close()
        return json.loads(row[0]) if row else None

    def put(self, file_hash: str, schema_version: str, model_family: str, prompt_contract_version: str, data: dict[str, Any]) -> None:
        conn = self._connect()
        conn.execute("INSERT OR REPLACE INTO cache(file_hash,schema_version,model_family,prompt_contract_version,data) VALUES(?,?,?,?,?)", (file_hash, schema_version, model_family, prompt_contract_version, json.dumps(data, sort_keys=True)))
        conn.commit(); conn.close()
