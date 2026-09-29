from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from engineering_office.ui_server import OfficeUIServer


def make_project(root: Path) -> Path:
    root.mkdir()
    (root / "README.md").write_text("# sample\n")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("VALUE = 1\n")
    (root / "acceptance.json").write_text(json.dumps({"gates": [], "required_evidence": []}))
    return root


def request(url: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {}, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())


def test_control_room_agent_and_floor_endpoints(tmp_path: Path):
    project = make_project(tmp_path / "p")
    server = OfficeUIServer(project, host="127.0.0.1", port=0, floor_registry_path=tmp_path / "floors.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        base = f"http://127.0.0.1:{server.port}"
        request(base + "/api/start", "POST", {"objective": "Complete"})
        _, snap = request(base + "/api/snapshot")
        agent = snap["status"]["agents"][0]["name"]
        encoded = urllib.parse.quote(agent, safe="")

        _, floors = request(base + "/api/floors")
        assert floors[0]["current"] is True
        _, detail = request(base + f"/api/agents/{encoded}")
        assert detail["agent"]["name"] == agent

        _, steer = request(base + f"/api/agents/{encoded}/steer", "POST", {"message": "Inspect evidence"})
        assert steer["recipient"] == agent
        _, paused = request(base + f"/api/agents/{encoded}/control/pause", "POST", {})
        assert paused["state"] == "paused"
        _, resumed = request(base + f"/api/agents/{encoded}/control/resume", "POST", {})
        assert resumed["state"] == "running"
    finally:
        server.shutdown(); thread.join(timeout=2)


def test_control_room_can_add_specialist_and_switch_floor(tmp_path: Path):
    a = make_project(tmp_path / "a")
    b = make_project(tmp_path / "b")
    server = OfficeUIServer(a, host="127.0.0.1", port=0, floor_registry_path=tmp_path / "floors.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        base = f"http://127.0.0.1:{server.port}"
        request(base + "/api/start", "POST", {"objective": "A"})
        _, added = request(base + "/api/add-agent", "POST", {"expertise": "robotics navigation"})
        assert "robotics" in " ".join(added["capabilities"]).lower()

        _, switched = request(base + "/api/floors", "POST", {"path": str(b)})
        assert switched["project_root"] == str(b.resolve())
        _, floors = request(base + "/api/floors")
        assert {Path(f["path"]).name for f in floors} == {"a", "b"}
    finally:
        server.shutdown(); thread.join(timeout=2)
