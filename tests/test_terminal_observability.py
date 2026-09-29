from __future__ import annotations

from pathlib import Path

from engineering_office.runtime_events import emit_runtime_event
from engineering_office.ui_service import DashboardService


def test_terminal_uses_real_events_and_bounds_large_output(tmp_path: Path):
    (tmp_path / "README.md").write_text("demo")
    service = DashboardService(tmp_path, floor_registry_path=tmp_path / "floors.json")
    service.start("inspect")
    project_id = service.engine._load_project().project_id
    emit_runtime_event(service.engine.runtime_events, project_id=project_id, agent_id="Coder", task_id="T", kind="command.started", summary="pytest", payload={"command":"pytest -q"}, source="tool")
    emit_runtime_event(service.engine.runtime_events, project_id=project_id, agent_id="Coder", task_id="T", kind="command.output", summary="output", payload={"stdout":"x" * 30000}, source="tool")
    terminal = service.agent_terminal("Coder", limit=20)
    assert terminal["entries"][0]["kind"] == "command.started"
    output = next(e for e in terminal["entries"] if e["kind"] == "command.output")
    assert output["truncated"] is True
    assert len(output["text"]) <= 12050


def test_terminal_redacts_secrets_and_does_not_expose_outside_path(tmp_path: Path):
    (tmp_path / "README.md").write_text("demo")
    service = DashboardService(tmp_path, floor_registry_path=tmp_path / "floors.json")
    service.start("inspect")
    project_id = service.engine._load_project().project_id
    emit_runtime_event(service.engine.runtime_events, project_id=project_id, agent_id="Coder", kind="file.read", summary="api_key=secret-value", payload={"path":"/etc/passwd", "token":"token=abc123"})
    terminal = service.agent_terminal("Coder")
    text = str(terminal)
    assert "secret-value" not in text
    assert "abc123" not in text
    assert "/etc/passwd" not in text
