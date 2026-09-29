from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from engineering_office.intake import IntakeError
from engineering_office.ui_service import DashboardService


def make_project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "README.md").write_text("# starter\n")
    return root


def make_service(tmp_path: Path) -> DashboardService:
    initial = make_project(tmp_path / "initial")
    return DashboardService(
        initial,
        floor_registry_path=tmp_path / "floors.json",
        intake_workspace_root=tmp_path / "managed",
        intake_staging_root=tmp_path / "staging",
    )


def test_intake_path_switches_to_zip_root_without_starting(tmp_path: Path):
    service = make_service(tmp_path)
    archive = tmp_path / "project.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("robot/package.xml", "<package/>")
        zf.writestr("robot/src/node.py", "print('x')\n")
    result = service.intake_path(str(archive), objective="inspect")
    assert result["kind"] == "archive"
    assert result["managed"] is True
    assert service.root.name == "robot"
    assert service.initialized is False
    assert not (service.root / ".office/project.json").exists()
    floors = service.list_floors()
    current = next(f for f in floors if f["current"])
    assert current["source_kind"] == "archive"
    assert current["managed"] is True


def test_failed_intake_does_not_register_floor(tmp_path: Path):
    service = make_service(tmp_path)
    before = {f["path"] for f in service.list_floors()}
    with pytest.raises(IntakeError):
        service.intake_path(str(tmp_path / "missing.zip"))
    after = {f["path"] for f in service.list_floors()}
    assert after == before


def test_paste_new_and_git_intake_use_same_activation_boundary(tmp_path: Path):
    service = make_service(tmp_path)
    pasted = service.intake_paste("tiny", "finish", [{"path": "main.py", "content": "X=1\n"}])
    assert pasted["kind"] == "paste"
    assert (service.root / "main.py").is_file()
    assert not service.initialized

    new = service.intake_new("green robot", "Build a small robot tool")
    assert new["kind"] == "new"
    assert (service.root / "PROJECT_BRIEF.md").is_file()
    assert not service.initialized

    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@local.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "README.md").write_text("repo")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    cloned = service.intake_git(str(repo), "clone", "inspect")
    assert cloned["kind"] == "git"
    assert (service.root / ".git").exists()
    assert not service.initialized


def test_upload_session_commit_activates_floor_and_keeps_provenance(tmp_path: Path):
    service = make_service(tmp_path)
    session = service.create_upload_session("upload robot", "inspect")
    sid = session["session_id"]
    service.upload_session_file(sid, "robot/src/main.py", b"print('ok')\n")
    result = service.commit_upload_session(sid)
    assert result["kind"] == "files"
    assert service.root.name == "robot"
    floor = next(f for f in service.list_floors() if f["current"])
    assert floor["source_kind"] == "files"
    assert floor["source_name"] == "browser-upload"


def test_existing_switch_project_still_works_and_preserves_floor_metadata(tmp_path: Path):
    service = make_service(tmp_path)
    other = make_project(tmp_path / "other")
    snap = service.switch_project(other)
    assert snap["project_root"] == str(other.resolve())
    assert service.list_floors()[0]["path"] == str(other.resolve())
