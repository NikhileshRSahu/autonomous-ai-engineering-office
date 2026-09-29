from __future__ import annotations

import json
from pathlib import Path

from engineering_office.floor_registry import FloorRegistry
from engineering_office.ui_service import DashboardService


def make_project(root: Path, name: str = "sample") -> Path:
    root.mkdir()
    (root / "README.md").write_text(f"# {name}\n")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("VALUE = 1\n")
    (root / "acceptance.json").write_text(json.dumps({"gates": [], "required_evidence": []}))
    return root


def test_floor_registry_deduplicates_and_marks_current(tmp_path: Path):
    registry = FloorRegistry(tmp_path / "floors.json")
    a = make_project(tmp_path / "a", "A")
    b = make_project(tmp_path / "b", "B")
    registry.touch(a)
    registry.touch(b)
    registry.touch(a)

    floors = registry.list(current=a)

    assert len(floors) == 2
    assert floors[0]["path"] == str(a.resolve())
    assert floors[0]["current"] is True
    assert {item["name"] for item in floors} == {"a", "b"}


def test_service_snapshot_exposes_floors_and_agent_controls(tmp_path: Path):
    project = make_project(tmp_path / "p")
    service = DashboardService(project, floor_registry_path=tmp_path / "floors.json")
    service.start("Complete")
    agent = service.snapshot()["status"]["agents"][0]["name"]
    service.pause_agent(agent)

    snap = service.snapshot()

    assert snap["floors"][0]["path"] == str(project.resolve())
    assert snap["agent_controls"][agent]["state"] == "paused"


def test_agent_detail_contains_inspector_surfaces_and_queue(tmp_path: Path):
    project = make_project(tmp_path / "p")
    service = DashboardService(project, floor_registry_path=tmp_path / "floors.json")
    started = service.start("Complete")
    agent = started["agents"][0]["name"]
    service.steer_agent(agent, "Check evidence first")

    detail = service.agent_detail(agent)

    assert detail["agent"]["name"] == agent
    assert set(detail) >= {"agent", "control", "task", "terminal", "files", "messages", "queue", "evidence", "traces"}
    assert detail["queue"][-1]["data"]["message"] == "Check evidence first"
    assert isinstance(detail["terminal"], list)
    assert isinstance(detail["files"], list)


def test_director_detail_is_selectable_without_fake_agent(tmp_path: Path):
    project = make_project(tmp_path / "p")
    service = DashboardService(project, floor_registry_path=tmp_path / "floors.json")
    service.start("Complete")

    detail = service.agent_detail("Office Director")

    assert detail["agent"]["name"] == "Office Director"
    assert detail["agent"]["role"] == "orchestrator"
    assert detail["task"] is None
    assert detail["traces"]


def test_add_agent_uses_factory_and_persists_roster(tmp_path: Path):
    project = make_project(tmp_path / "p")
    service = DashboardService(project, floor_registry_path=tmp_path / "floors.json")
    service.start("Complete")

    added = service.add_agent("PostgreSQL concurrency")

    assert "PostgreSQL" in added["name"]
    assert any(a["name"] == added["name"] for a in service.snapshot()["status"]["agents"])


def test_switch_project_registers_independent_floor(tmp_path: Path):
    a = make_project(tmp_path / "a")
    b = make_project(tmp_path / "b")
    service = DashboardService(a, floor_registry_path=tmp_path / "floors.json")
    service.start("Project A")
    service.switch_project(b)
    service.start("Project B")

    floors = service.list_floors()

    assert {Path(f["path"]).name for f in floors} == {"a", "b"}
    assert next(f for f in floors if f["current"])["path"] == str(b.resolve())
