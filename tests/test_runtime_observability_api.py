from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from engineering_office.runtime_events import emit_runtime_event
from engineering_office.ui_server import OfficeUIServer
from engineering_office.ui_service import DashboardService


def _initialized(root: Path) -> DashboardService:
    (root / "README.md").write_text("# demo\n")
    (root / "acceptance.json").write_text(json.dumps({"gates": [{"name":"ok","command":"python -c \"print('OK')\"","required_output":"OK"}], "required_evidence": []}))
    service = DashboardService(root, floor_registry_path=root / "floors.json")
    service.start("verify project")
    return service


def test_events_are_incremental_and_filterable(tmp_path: Path):
    service = _initialized(tmp_path)
    project_id = service.engine._load_project().project_id
    one = emit_runtime_event(service.engine.runtime_events, project_id=project_id, agent_id="A", task_id="T", kind="file.read", summary="read one")
    two = emit_runtime_event(service.engine.runtime_events, project_id=project_id, agent_id="B", task_id="T", kind="file.written", summary="write two")
    payload = service.events(after=one.id, task_id="T")
    assert [e["id"] for e in payload["events"]] == [two.id]
    assert payload["cursor"] == two.id
    assert service.events(agent_id="A")["events"][-1]["agent_id"] == "A"


def test_activity_and_model_runtime_are_derived_from_events(tmp_path: Path):
    service = _initialized(tmp_path)
    project_id = service.engine._load_project().project_id
    emit_runtime_event(service.engine.runtime_events, project_id=project_id, agent_id="ROS", kind="research.started", summary="research docs")
    emit_runtime_event(service.engine.runtime_events, project_id=project_id, kind="model.loading", summary="qwen loading", payload={"model":"qwen"}, source="model")
    assert service.agent_activity("ROS")["phase"] == "RESEARCHING"
    assert service.agent_activity("ROS")["location"] == "research"
    assert service.models_runtime()["models"]["qwen"]["phase"] == "MODEL_LOADING"


def test_http_events_endpoint_works(tmp_path: Path):
    (tmp_path / "README.md").write_text("# demo\n")
    server = OfficeUIServer(tmp_path, port=0, floor_registry_path=tmp_path / "floors.json")
    server.service.start("inspect")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/api/events/recent") as response:
            data = json.load(response)
        assert data["events"]
        assert data["cursor"] == data["events"][-1]["id"]
    finally:
        server.shutdown(); thread.join(timeout=2)
