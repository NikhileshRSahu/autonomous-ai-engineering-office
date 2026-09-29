from __future__ import annotations

import json
from pathlib import Path

from engineering_office.communications import MessageKind
from engineering_office.office import OfficeEngine
from engineering_office.runtime_events import RuntimeEventStore


def _project(root: Path) -> OfficeEngine:
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('ok')\n")
    (root / "README.md").write_text("# tiny\n")
    (root / "acceptance.json").write_text(json.dumps({
        "gates": [{"name": "ok", "command": "python -c \"print('OK')\"", "expected_exit": 0, "required_output": "OK"}],
        "required_evidence": [],
    }))
    engine = OfficeEngine(root)
    engine.start("inspect and verify")
    return engine


def test_start_emits_normalized_project_events(tmp_path: Path):
    engine = _project(tmp_path)
    events = RuntimeEventStore(tmp_path).read()
    kinds = [event.kind for event in events]
    assert kinds[:3] == ["project.discovered", "project.staffed", "project.planned"]


def test_real_tools_emit_file_and_command_events(tmp_path: Path):
    engine = _project(tmp_path)
    project = engine._load_project()
    agent = next(a for a in engine._load_agents() if "filesystem.read" in a.allowed_tools and "shell" in a.allowed_tools)
    tools = engine._tools_for(agent, project.project_id, "T-X")
    tools.execute("filesystem.read", {"path": "README.md"})
    tools.execute("shell", {"command": "python -c \"print('hello')\""})
    events = RuntimeEventStore(tmp_path).read(task_id="T-X")
    kinds = [e.kind for e in events]
    assert "file.read" in kinds
    assert "command.started" in kinds
    assert "command.output" in kinds
    assert "command.finished" in kinds
    assert next(e for e in events if e.kind == "command.finished").payload["returncode"] == 0


def test_durable_message_emits_runtime_handoff(tmp_path: Path):
    engine = _project(tmp_path)
    project = engine._load_project()
    engine.comms.send(project.project_id, "T-1", "A", "B", MessageKind.ACTION, {"message": "review evidence"})
    events = RuntimeEventStore(tmp_path).read(task_id="T-1")
    event = next(e for e in events if e.kind == "message.sent")
    assert event.payload["sender"] == "A"
    assert event.payload["recipient"] == "B"


def test_verification_events_are_authoritative(tmp_path: Path):
    engine = _project(tmp_path)
    report = engine.verify()
    events = RuntimeEventStore(tmp_path).read()
    started = [e for e in events if e.kind == "verification.started"]
    finished = [e for e in events if e.kind == "verification.finished"]
    assert started and finished
    assert finished[-1].payload["status"] == report["verdict"]
    assert finished[-1].phase == "VERIFIED"
