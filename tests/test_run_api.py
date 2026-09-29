from __future__ import annotations
import json, threading, urllib.request
from pathlib import Path

from engineering_office.ui_server import OfficeUIServer


def get(url):
    with urllib.request.urlopen(url,timeout=3) as r: return json.load(r)


def test_run_index_residency_and_needs_user_apis(tmp_path: Path):
    from engineering_office.run_records import RunCoordinator
    from engineering_office.project_index import ProjectIndex
    (tmp_path/"README.md").write_text("# p")
    rc=RunCoordinator(tmp_path,project_id="P-1"); rc.start("fast-audit","audit",["IMPORT","REPORT"])
    ProjectIndex(tmp_path).update()
    server=OfficeUIServer(tmp_path,port=0,floor_registry_path=tmp_path/"floors.json")
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        base=f"http://127.0.0.1:{server.port}"
        assert get(base+"/api/run")["run_id"].startswith("RUN-")
        assert get(base+"/api/run/timing")["total_elapsed_seconds"] >= 0
        assert get(base+"/api/index/status")["file_count"] >= 1
        assert "models" in get(base+"/api/models/residency")
        assert get(base+"/api/needs-user")["count"] == 0
    finally:
        server.shutdown(); thread.join(timeout=2)
