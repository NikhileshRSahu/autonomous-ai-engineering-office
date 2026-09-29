from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from engineering_office.ui_server import OfficeUIServer


def make_project(root: Path) -> Path:
    root.mkdir()
    (root / "README.md").write_text("# sample\n")
    (root / "acceptance.json").write_text(json.dumps({"gates": [], "required_evidence": []}))
    return root


def fetch(url: str):
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read()


def test_server_serves_health_dashboard_and_snapshot(tmp_path: Path):
    project = make_project(tmp_path / "p")
    server = OfficeUIServer(project, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.port}"
        status, content_type, body = fetch(base + "/api/health")
        assert status == 200
        assert json.loads(body)["ok"] is True
        status, content_type, body = fetch(base + "/api/snapshot")
        assert json.loads(body)["project_root"] == str(project.resolve())
        status, content_type, body = fetch(base + "/")
        assert status == 200
        assert "text/html" in content_type
        assert b"Engineering Office" in body
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_static_path_traversal_is_denied(tmp_path: Path):
    project = make_project(tmp_path / "p")
    server = OfficeUIServer(project, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(Exception):
            fetch(f"http://127.0.0.1:{server.port}/static/../pyproject.toml")
    finally:
        server.shutdown(); thread.join(timeout=2)

def post_json(url: str, payload: dict):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())


def test_server_updates_model_config_and_serves_offline_assets(tmp_path: Path):
    project = make_project(tmp_path / "p")
    server = OfficeUIServer(project, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        base=f"http://127.0.0.1:{server.port}"
        status, _, css = fetch(base+"/static/app.css")
        assert status == 200 and b"--accent" in css
        status, _, js = fetch(base+"/static/app.js")
        assert status == 200 and b"Office" in js
        payload={"model_profiles":{},"routing":{},"max_feedback_cycles":4,"max_task_iterations":6,"parallelism":4}
        status, body=post_json(base+"/api/config",payload)
        assert status==200 and body["parallelism"]==4
    finally:
        server.shutdown(); thread.join(timeout=2)
