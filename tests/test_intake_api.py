from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from engineering_office.ui_server import OfficeUIServer


def make_project(path: Path) -> Path:
    path.mkdir(); (path / "README.md").write_text("starter")
    return path


def request(url: str, method: str = "GET", payload=None, raw: bytes | None = None, content_type: str | None = None):
    if raw is not None:
        data = raw
        headers = {"Content-Type": content_type or "application/octet-stream"}
    elif payload is not None:
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
    else:
        data = None; headers = {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, json.loads(body) if body else None


def make_server(tmp_path: Path):
    project = make_project(tmp_path / "initial")
    server = OfficeUIServer(
        project,
        host="127.0.0.1",
        port=0,
        floor_registry_path=tmp_path / "floors.json",
        intake_workspace_root=tmp_path / "managed",
        intake_staging_root=tmp_path / "staging",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    return server, thread, f"http://127.0.0.1:{server.port}"


def test_json_intake_routes_cover_path_paste_new(tmp_path: Path):
    server, thread, base = make_server(tmp_path)
    try:
        folder = make_project(tmp_path / "folder")
        status, body = request(base + "/api/intake/path", "POST", {"path": str(folder), "objective": "inspect"})
        assert status == 200 and body["kind"] == "directory" and body["initialized"] is False

        archive = tmp_path / "robot.zip"
        with zipfile.ZipFile(archive, "w") as zf: zf.writestr("robot/main.py", "X=1")
        status, body = request(base + "/api/intake/path", "POST", {"path": str(archive), "objective": "inspect"})
        assert status == 200 and body["kind"] == "archive" and Path(body["root"]).name == "robot"

        status, body = request(base + "/api/intake/paste", "POST", {"name": "paste", "objective": "finish", "items": [{"path": "main.py", "content": "X=1"}]})
        assert status == 200 and body["kind"] == "paste"

        status, body = request(base + "/api/intake/new", "POST", {"name": "new", "objective": "Build something small"})
        assert status == 200 and body["kind"] == "new"
    finally:
        server.shutdown(); thread.join(timeout=2)


def test_streaming_upload_session_round_trip_and_cancel(tmp_path: Path):
    server, thread, base = make_server(tmp_path)
    try:
        status, created = request(base + "/api/intake/sessions", "POST", {"name": "upload", "objective": "inspect"})
        assert status == 200
        sid = created["session_id"]
        rel = urllib.parse.quote("robot/src/main.py", safe="")
        status, uploaded = request(base + f"/api/intake/sessions/{sid}/file?path={rel}", "POST", raw=b"print('ok')\n")
        assert status == 200 and uploaded["size"] == 12
        status, committed = request(base + f"/api/intake/sessions/{sid}/commit", "POST", {})
        assert status == 200 and committed["kind"] == "files" and Path(committed["root"]).name == "robot"

        _, created2 = request(base + "/api/intake/sessions", "POST", {})
        status, cancelled = request(base + f"/api/intake/sessions/{created2['session_id']}", "DELETE")
        assert status == 200 and cancelled["cancelled"] is True
    finally:
        server.shutdown(); thread.join(timeout=2)


def test_intake_errors_have_stable_code_and_legacy_project_route_remains(tmp_path: Path):
    server, thread, base = make_server(tmp_path)
    try:
        status, body = request(base + "/api/intake/path", "POST", {"path": str(tmp_path / "missing.zip")})
        assert status == 400
        assert body["error"] == "IntakeError" and body["code"] == "SOURCE_NOT_FOUND"
        assert "message" in body

        folder = make_project(tmp_path / "legacy")
        status, body = request(base + "/api/project", "POST", {"path": str(folder)})
        assert status == 200 and body["project_root"] == str(folder.resolve())
    finally:
        server.shutdown(); thread.join(timeout=2)


def test_upload_traversal_is_rejected_by_http_api(tmp_path: Path):
    server, thread, base = make_server(tmp_path)
    try:
        _, created = request(base + "/api/intake/sessions", "POST", {})
        sid = created["session_id"]
        status, body = request(base + f"/api/intake/sessions/{sid}/file?path=..%2Foutside.txt", "POST", raw=b"bad")
        assert status == 400 and body["code"] == "UPLOAD_INVALID_PATH"
        assert not (tmp_path / "outside.txt").exists()
    finally:
        server.shutdown(); thread.join(timeout=2)
