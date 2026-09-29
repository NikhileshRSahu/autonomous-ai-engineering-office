from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest

from engineering_office.intake import IntakeError, IntakeKind, IntakeSessionManager, UniversalIntakeService


def make_manager(tmp_path: Path, **kwargs) -> IntakeSessionManager:
    service = UniversalIntakeService(
        workspace_root=tmp_path / "workspaces",
        staging_root=tmp_path / "staging",
        max_files=kwargs.pop("max_files", 10),
        max_uncompressed_bytes=kwargs.pop("max_bytes", 1024),
    )
    return IntakeSessionManager(service, session_ttl_seconds=kwargs.pop("ttl", 3600))


def test_session_create_upload_commit_preserves_directory_paths(tmp_path: Path):
    manager = make_manager(tmp_path)
    session = manager.create(display_name="robot", objective="inspect")
    manager.upload(session["session_id"], "robot/src/main.py", b"print('ok')\n")
    manager.upload(session["session_id"], "robot/README.md", io.BytesIO(b"hello"), size=5)
    result = manager.commit(session["session_id"])
    assert result.kind is IntakeKind.FILES
    assert result.root.name == "robot"
    assert (result.root / "src/main.py").read_text() == "print('ok')\n"
    assert (result.root / "README.md").read_text() == "hello"
    assert not Path(session["staging_dir"]).exists()


def test_session_rejects_traversal_before_write(tmp_path: Path):
    manager = make_manager(tmp_path)
    sid = manager.create()["session_id"]
    with pytest.raises(IntakeError) as exc:
        manager.upload(sid, "../outside.txt", b"bad")
    assert exc.value.code == "UPLOAD_INVALID_PATH"
    assert not (tmp_path / "outside.txt").exists()


def test_session_rejects_duplicate_path(tmp_path: Path):
    manager = make_manager(tmp_path)
    sid = manager.create()["session_id"]
    manager.upload(sid, "a.txt", b"one")
    with pytest.raises(IntakeError) as exc:
        manager.upload(sid, "a.txt", b"two")
    assert exc.value.code == "UPLOAD_INVALID_PATH"


def test_session_enforces_file_and_byte_limits_incrementally(tmp_path: Path):
    manager = make_manager(tmp_path, max_files=1, max_bytes=4)
    sid = manager.create()["session_id"]
    manager.upload(sid, "a.txt", b"1234")
    with pytest.raises(IntakeError) as exc:
        manager.upload(sid, "b.txt", b"x")
    assert exc.value.code == "LIMIT_EXCEEDED"

    sid2 = manager.create()["session_id"]
    with pytest.raises(IntakeError) as exc:
        manager.upload(sid2, "large.txt", b"12345")
    assert exc.value.code == "LIMIT_EXCEEDED"


def test_cancel_removes_staging(tmp_path: Path):
    manager = make_manager(tmp_path)
    session = manager.create()
    manager.upload(session["session_id"], "a.txt", b"x")
    path = Path(session["staging_dir"])
    assert path.exists()
    manager.cancel(session["session_id"])
    assert not path.exists()


def test_stale_session_cleanup_removes_old_staging(tmp_path: Path):
    manager = make_manager(tmp_path, ttl=1)
    session = manager.create()
    path = Path(session["staging_dir"])
    old = time.time() - 10
    os.utime(path, (old, old))
    removed = manager.cleanup_stale(now=time.time())
    assert session["session_id"] in removed
    assert not path.exists()


def test_unknown_or_empty_session_is_actionable(tmp_path: Path):
    manager = make_manager(tmp_path)
    with pytest.raises(IntakeError) as exc:
        manager.commit("missing")
    assert exc.value.code == "UPLOAD_INCOMPLETE"
    sid = manager.create()["session_id"]
    with pytest.raises(IntakeError) as exc:
        manager.commit(sid)
    assert exc.value.code == "UPLOAD_INCOMPLETE"

def test_archive_upload_session_extracts_single_uploaded_archive(tmp_path: Path):
    import zipfile
    manager = make_manager(tmp_path)
    archive = tmp_path / "robot.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("robot/package.xml", "<package/>")
        zf.writestr("robot/src/node.py", "print('ok')\n")
    session = manager.create(display_name="robot", objective="inspect", mode="archive")
    manager.upload(session["session_id"], "robot.zip", archive.read_bytes())
    result = manager.commit(session["session_id"])
    assert result.kind is IntakeKind.ARCHIVE
    assert result.root.name == "robot"
    assert (result.root / "src/node.py").is_file()
