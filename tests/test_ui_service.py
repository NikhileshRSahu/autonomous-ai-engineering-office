from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from engineering_office.ui_service import DashboardService, JobManager


def make_project(root: Path) -> Path:
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("VALUE = 1\n")
    (root / "acceptance.json").write_text(json.dumps({"gates": [], "required_evidence": []}))
    return root


def test_snapshot_before_start_is_onboarding(tmp_path: Path):
    project = make_project(tmp_path / "p")
    snap = DashboardService(project).snapshot()
    assert snap["initialized"] is False
    assert snap["project_root"] == str(project.resolve())
    assert snap["control"] == {"paused": False, "stopped": False}


def test_snapshot_after_start_contains_control_room_data(tmp_path: Path):
    project = make_project(tmp_path / "p")
    service = DashboardService(project)
    service.start("Complete this project")
    snap = service.snapshot()
    assert snap["initialized"] is True
    assert snap["status"]["objective"] == "Complete this project"
    assert snap["status"]["agents"]
    assert snap["status"]["tasks"]
    assert isinstance(snap["events"], list)
    assert isinstance(snap["approvals"], list)
    assert isinstance(snap["memory"], list)
    assert "config" in snap


def test_control_and_approval_actions_use_existing_authority(tmp_path: Path):
    project = make_project(tmp_path / "p")
    service = DashboardService(project)
    service.start("Complete")
    service.pause()
    assert service.snapshot()["control"]["paused"] is True
    service.resume()
    assert service.snapshot()["control"]["paused"] is False
    req = service.engine.approvals.request("rm important.txt", "HIGH", "destructive action")
    decided = service.decide_approval(req.approval_id, "approve")
    assert decided["status"] == "APPROVED"


def test_switch_project_rejects_missing_directory(tmp_path: Path):
    service = DashboardService(tmp_path)
    with pytest.raises(ValueError):
        service.switch_project(tmp_path / "missing")


def test_job_manager_runs_long_operation_without_blocking():
    jobs = JobManager()
    job_id = jobs.submit("slow", lambda: (time.sleep(0.05), {"ok": True})[1])
    first = jobs.get(job_id)
    assert first["state"] in {"RUNNING", "PASS"}
    deadline = time.time() + 2
    while time.time() < deadline:
        result = jobs.get(job_id)
        if result["state"] != "RUNNING":
            break
        time.sleep(0.01)
    assert result["state"] == "PASS"
    assert result["result"] == {"ok": True}

def test_update_config_is_file_backed_and_visible(tmp_path: Path):
    project = make_project(tmp_path / "p")
    service = DashboardService(project)
    service.start("Complete")
    config = {
        "model_profiles": {
            "local": {"endpoint": "http://127.0.0.1:1234/v1", "model": "local-model"}
        },
        "routing": {"LOW": "local", "MEDIUM": "local", "HIGH": "local", "ESCALATION": "local"},
        "max_feedback_cycles": 5,
        "max_task_iterations": 7,
        "parallelism": 3,
    }
    saved = service.update_config(config)
    assert saved["parallelism"] == 3
    assert service.snapshot()["config"]["model_profiles"]["local"]["model"] == "local-model"
