from __future__ import annotations

import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from engineering_office.intake import (
    IntakeError,
    IntakeKind,
    UniversalIntakeService,
)


def service(tmp_path: Path, **kwargs) -> UniversalIntakeService:
    return UniversalIntakeService(
        workspace_root=tmp_path / "workspaces",
        staging_root=tmp_path / "staging",
        **kwargs,
    )


def zip_file(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_directory_intake_stays_in_place(tmp_path: Path):
    project = tmp_path / "project"; project.mkdir(); (project / "README.md").write_text("x")
    result = service(tmp_path).from_path(project)
    assert result.kind is IntakeKind.DIRECTORY
    assert result.root == project.resolve()
    assert result.managed is False


def test_missing_source_has_stable_error_code(tmp_path: Path):
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(tmp_path / "missing")
    assert exc.value.code == "SOURCE_NOT_FOUND"


def test_safe_zip_extracts_and_detects_single_project_root(tmp_path: Path):
    archive = tmp_path / "sample.zip"
    zip_file(archive, {"repo/pyproject.toml": "[project]\nname='x'\n", "repo/src/app.py": "X=1\n"})
    result = service(tmp_path).from_path(archive)
    assert result.kind is IntakeKind.ARCHIVE
    assert result.managed is True
    assert result.root.name == "repo"
    assert (result.root / "src/app.py").read_text() == "X=1\n"
    assert result.extracted_files == 2
    assert (result.root / ".office/intake.json").is_file()


def test_corrupt_zip_returns_archive_corrupt(tmp_path: Path):
    archive = tmp_path / "bad.zip"; archive.write_bytes(b"not zip")
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(archive)
    assert exc.value.code == "ARCHIVE_CORRUPT"


def test_zip_traversal_and_symlink_are_rejected(tmp_path: Path):
    traversal = tmp_path / "escape.zip"; zip_file(traversal, {"../owned": "bad"})
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(traversal)
    assert exc.value.code == "ARCHIVE_UNSAFE"
    assert not (tmp_path / "owned").exists()

    link = tmp_path / "link.zip"
    with zipfile.ZipFile(link, "w") as zf:
        info = zipfile.ZipInfo("repo/link")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "../../outside")
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(link)
    assert exc.value.code == "ARCHIVE_UNSAFE"

    fifo = tmp_path / "fifo.zip"
    with zipfile.ZipFile(fifo, "w") as zf:
        info = zipfile.ZipInfo("repo/pipe")
        info.create_system = 3
        info.external_attr = (0o010644 << 16)
        zf.writestr(info, b"")
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(fifo)
    assert exc.value.code == "ARCHIVE_UNSAFE"


def test_tar_extracts_but_traversal_and_links_are_rejected(tmp_path: Path):
    good = tmp_path / "good.tar.gz"
    with tarfile.open(good, "w:gz") as tf:
        payload = b"hello"
        info = tarfile.TarInfo("repo/README.md"); info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    result = service(tmp_path).from_path(good)
    assert (result.root / "README.md").read_text() == "hello"

    bad = tmp_path / "bad.tar"
    with tarfile.open(bad, "w") as tf:
        payload = b"bad"; info = tarfile.TarInfo("../escape"); info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(bad)
    assert exc.value.code == "ARCHIVE_UNSAFE"

    linked = tmp_path / "linked.tar"
    with tarfile.open(linked, "w") as tf:
        info = tarfile.TarInfo("repo/link"); info.type = tarfile.SYMTYPE; info.linkname = "../../outside"
        tf.addfile(info)
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(linked)
    assert exc.value.code == "ARCHIVE_UNSAFE"


def test_archive_limits_are_enforced(tmp_path: Path):
    archive = tmp_path / "many.zip"; zip_file(archive, {"a": "1", "b": "2"})
    with pytest.raises(IntakeError) as exc:
        service(tmp_path, max_files=1).from_path(archive)
    assert exc.value.code == "LIMIT_EXCEEDED"

    archive2 = tmp_path / "large.zip"; zip_file(archive2, {"a": "12345"})
    with pytest.raises(IntakeError) as exc:
        service(tmp_path, max_uncompressed_bytes=4).from_path(archive2)
    assert exc.value.code == "LIMIT_EXCEEDED"


def test_ambiguous_archive_keeps_extraction_root(tmp_path: Path):
    archive = tmp_path / "mono.zip"
    zip_file(archive, {"api/pyproject.toml": "x", "web/package.json": "{}"})
    result = service(tmp_path).from_path(archive)
    assert (result.root / "api/pyproject.toml").is_file()
    assert (result.root / "web/package.json").is_file()
    assert result.root.name not in {"api", "web"}


def test_single_file_and_paste_create_managed_workspaces(tmp_path: Path):
    single = tmp_path / "script.py"; single.write_text("print('x')\n")
    result = service(tmp_path).from_path(single)
    assert result.kind is IntakeKind.FILES and result.managed
    assert (result.root / "script.py").read_text() == "print('x')\n"

    pasted = service(tmp_path).from_paste(
        name="tiny app",
        objective="make it run",
        items=[{"path": "src/main.py", "content": "print('ok')\n"}, {"path": "README.md", "content": "hello"}],
    )
    assert pasted.kind is IntakeKind.PASTE
    assert (pasted.root / "src/main.py").read_text() == "print('ok')\n"
    assert (pasted.root / "README.md").read_text() == "hello"


def test_paste_unsafe_path_is_rejected(tmp_path: Path):
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_paste(name="x", objective="x", items=[{"path": "../escape.py", "content": "x"}])
    assert exc.value.code == "UPLOAD_INVALID_PATH"
    assert not (tmp_path / "escape.py").exists()


def test_greenfield_requires_objective_and_creates_brief(tmp_path: Path):
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_new(name="robot", objective="  ")
    assert exc.value.code == "OBJECTIVE_REQUIRED"
    result = service(tmp_path).from_new(name="robot nav", objective="Build a ROS 2 navigation demo")
    assert result.kind is IntakeKind.NEW and result.managed
    brief = (result.root / "PROJECT_BRIEF.md").read_text()
    assert "Build a ROS 2 navigation demo" in brief


def test_git_clone_preserves_history_and_failure_cleans_workspace(tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "t@local.invalid"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=source, check=True)
    (source / "README.md").write_text("repo")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=source, check=True)

    result = service(tmp_path).from_git(str(source), name="cloned")
    assert result.kind is IntakeKind.GIT and result.managed
    assert (result.root / ".git").is_dir()
    assert subprocess.check_output(["git", "log", "-1", "--format=%s"], cwd=result.root, text=True).strip() == "initial"

    before = set((tmp_path / "workspaces").iterdir())
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_git("https://user:supersecret@127.0.0.1:1/nope.git", name="bad")
    assert exc.value.code == "GIT_CLONE_FAILED"
    assert "supersecret" not in str(exc.value)
    after = set((tmp_path / "workspaces").iterdir())
    assert after == before


def test_unknown_archive_extension_is_actionable(tmp_path: Path):
    path = tmp_path / "project.7z"; path.write_bytes(b"x")
    with pytest.raises(IntakeError) as exc:
        service(tmp_path).from_path(path, treat_as_archive=True)
    assert exc.value.code == "UNSUPPORTED_ARCHIVE"
