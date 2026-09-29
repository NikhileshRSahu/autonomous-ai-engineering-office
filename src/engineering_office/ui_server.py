from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
import json

import re
def render_report_html(md: str) -> str:
    md = md.replace('<', '&lt;').replace('>', '&gt;')
    md = __import__('re').sub(r'(?m)^# (.*)$', r'<h1>\1</h1>', md)
    md = __import__('re').sub(r'(?m)^## (.*)$', r'<h2 class="section-title">\1</h2>', md)
    md = __import__('re').sub(r'(?m)^### (.*)$', r'<h3>\1</h3>', md)
    md = __import__('re').sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', md)
    md = __import__('re').sub(r'(?m)^- \[(.*?)\] (.*)$', r'<div class="report-item"><span class="badge \1">\1</span> <span>\2</span></div>', md)
    md = __import__('re').sub(r'(?m)^- (.*)$', r'<li>\1</li>', md)
    md = __import__('re').sub(r'(?m)^&gt; (.*)$', r'<blockquote>\1</blockquote>', md)
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Engineering Report</title>
    <style>
        body {{ font-family: system-ui, sans-serif; background: #f7f1df; color: #28332f; line-height: 1.6; max-width: 900px; margin: 40px auto; padding: 20px; }}
        h1 {{ border-bottom: 2px solid #28332f; padding-bottom: 10px; font-size: 28px; }}
        .section-title {{ background: #28332f; color: #f7f1df; padding: 8px 12px; font-size: 18px; margin-top: 40px; display: inline-block; letter-spacing: 0.1em; }}
        .report-item {{ display: flex; gap: 10px; padding: 8px; border-bottom: 1px solid #dcd3b6; align-items: flex-start; }}
        .badge {{ padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; text-transform: uppercase; }}
        .info {{ background: #cce5ff; color: #004085; }}
        .warning {{ background: #fff3cd; color: #856404; }}
        .blocker, .error {{ background: #f8d7da; color: #721c24; }}
        blockquote {{ border-left: 4px solid #28332f; margin: 0; padding-left: 16px; font-style: italic; color: #5d405f; }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 6px; }}
    </style>
</head>
<body>
    {md}
</body>
</html>'''
    return html


import mimetypes

from .ui_service import DashboardService, JobManager
from .intake import IntakeError


_UI_DIR = Path(__file__).with_name("ui")


class OfficeUIServer:
    def __init__(
        self,
        project_root: str | Path,
        host: str = "127.0.0.1",
        port: int = 8765,
        floor_registry_path: str | Path | None = None,
        intake_workspace_root: str | Path | None = None,
        intake_staging_root: str | Path | None = None,
        intake_max_files: int = 100_000,
        intake_max_bytes: int = 8 * 1024 * 1024 * 1024,
        intake_session_ttl: int = 24 * 60 * 60,
    ):
        self.service = DashboardService(
            project_root,
            floor_registry_path=floor_registry_path,
            intake_workspace_root=intake_workspace_root,
            intake_staging_root=intake_staging_root,
            intake_max_files=intake_max_files,
            intake_max_bytes=intake_max_bytes,
            intake_session_ttl=intake_session_ttl,
        )
        self.jobs = JobManager()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "EngineeringOfficeUI/1.0"

            def log_message(self, format: str, *args: Any) -> None:
                # Keep terminal output focused; callers can inspect API/event state.
                return

            def _json(self, data: Any, status: int = 200) -> None:
                payload = json.dumps(data, indent=2, default=str).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length == 0:
                    return {}
                raw = self.rfile.read(length)
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError("request body must be JSON") from exc
                if not isinstance(data, dict):
                    raise ValueError("request body must be a JSON object")
                return data

            def _file(self, path: Path, content_type: str | None = None) -> None:
                if not path.is_file():
                    self.send_error(404)
                    return
                data = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                try:
                    parsed = urlparse(self.path)
                    path = unquote(parsed.path)
                    if path == "/api/health":
                        self._json({"ok": True, "project_root": str(outer.service.root), "port": outer.port})
                    elif path == "/api/snapshot":
                        snap = outer.service.snapshot()
                        snap["jobs"] = outer.jobs.list()
                        self._json(snap)
                    elif path == "/api/floors":
                        self._json(outer.service.list_floors())
                    elif path == "/api/events":
                        q = parse_qs(parsed.query)
                        self._json(outer.service.events(after=q.get("after", [None])[0], agent_id=q.get("agent_id", [None])[0], task_id=q.get("task_id", [None])[0], limit=int(q.get("limit", [500])[0])))
                    elif path == "/api/events/recent":
                        q = parse_qs(parsed.query)
                        self._json(outer.service.recent_events(limit=int(q.get("limit", [250])[0])))
                    elif path == "/api/models/runtime":
                        self._json(outer.service.models_runtime())
                    elif path == "/api/run":
                        self._json(outer.service.current_run() or {})
                    elif path == "/api/run/timing":
                        self._json(outer.service.run_timing())
                    elif path == "/api/run/report":
                        self._json(outer.service.run_report())
                    elif path == "/api/index/status":
                        self._json(outer.service.index_status())
                    elif path == "/api/models/residency":
                        self._json(outer.service.models_residency())
                    elif path == "/api/providers/status":
                        self._json(outer.service.provider_status())
                    elif path == "/api/needs-user":
                        self._json(outer.service.needs_user())
                    elif path == "/api/replay":
                        q=parse_qs(parsed.query)
                        self._json(outer.service.replay_events(q.get("start",[None])[0], q.get("end",[None])[0], agent_id=q.get("agent_id",[None])[0], task_id=q.get("task_id",[None])[0], limit=int(q.get("limit",[5000])[0])))
                    elif path == "/api/timeline":
                        q=parse_qs(parsed.query)
                        self._json(outer.service.timeline(agent_id=q.get("agent_id",[None])[0], task_id=q.get("task_id",[None])[0], category=q.get("category",[None])[0], limit=int(q.get("limit",[500])[0])))
                    elif path.startswith("/api/agents/"):
                        parts = [part for part in path.split("/") if part]
                        if len(parts) == 4 and parts[3] == "terminal":
                            q = parse_qs(parsed.query)
                            self._json(outer.service.agent_terminal(parts[2], after=q.get("after", [None])[0], limit=int(q.get("limit", [300])[0])))
                        elif len(parts) == 4 and parts[3] == "activity":
                            self._json(outer.service.agent_activity(parts[2]))
                        elif len(parts) == 3:
                            self._json(outer.service.agent_detail(parts[2]))
                        else:
                            raise ValueError("invalid agent endpoint")
                    elif path.startswith("/api/jobs/"):
                        self._json(outer.jobs.get(path.rsplit("/", 1)[-1]))
                    elif path == "/api/report/html":
                        rel = parse_qs(parsed.query).get("path", [""])[0]
                        data, content_type = outer.service.office_file(rel)
                        html = render_report_html(data.decode("utf-8", errors="replace"))
                        encoded = html.encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(encoded)))
                        self.end_headers()
                        self.wfile.write(encoded)
                    elif path == "/api/artifact":
                        rel = parse_qs(parsed.query).get("path", [""])[0]
                        data, content_type = outer.service.office_file(rel)
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers(); self.wfile.write(data)
                    elif path in {"/", "/index.html"}:
                        self._file(_UI_DIR / "index.html", "text/html; charset=utf-8")
                    elif path == "/manifest.json":
                        self._file(_UI_DIR / "manifest.json", "application/manifest+json")
                    elif path in {"/static/app.css", "/static/app.js"}:
                        self._file(_UI_DIR / Path(path).name)
                    elif path == "/static/living-floor-renderer.min.js":
                        self._file(_UI_DIR / "vendor" / "living-floor-renderer.min.js", "application/javascript; charset=utf-8")
                    else:
                        self.send_error(404)
                except KeyError as exc:
                    self._json({"error": "NotFound", "message": str(exc)}, 404)
                except (ValueError, FileNotFoundError) as exc:
                    self._json({"error": type(exc).__name__, "message": str(exc)}, 400)
                except Exception as exc:
                    self._json({"error": type(exc).__name__, "message": str(exc)}, 500)

            def do_POST(self) -> None:  # noqa: N802
                try:
                    parsed = urlparse(self.path)
                    path = unquote(parsed.path)
                    parts = [part for part in path.split("/") if part]

                    # Upload file bodies are raw bytes, not JSON. Stream directly
                    # into the bounded session manager instead of buffering/base64.
                    if len(parts) == 5 and parts[:3] == ["api", "intake", "sessions"] and parts[4] == "file":
                        session_id = parts[3]
                        rel = parse_qs(parsed.query).get("path", [""])[0]
                        if not rel:
                            raise IntakeError("upload path is required", "UPLOAD_INVALID_PATH")
                        raw_size = self.headers.get("Content-Length") or self.headers.get("X-Office-File-Size")
                        length = int(raw_size) if raw_size is not None else None
                        result = outer.service.upload_session_file(session_id, rel, self.rfile, size=length)
                        self._json(result)
                        return

                    body = self._body()
                    if path == "/api/intake/path":
                        result = outer.service.intake_path(body["path"], str(body.get("objective", "")))
                    elif path == "/api/intake/files":
                        paths = body.get("paths", [])
                        if not isinstance(paths, list):
                            raise ValueError("paths must be a list")
                        result = outer.service.intake_files(paths, str(body.get("objective", "")), body.get("name"))
                    elif path == "/api/intake/paste":
                        items = body.get("items", [])
                        if not isinstance(items, list):
                            raise ValueError("items must be a list")
                        result = outer.service.intake_paste(body.get("name"), str(body.get("objective", "")), items)
                    elif path == "/api/intake/git":
                        result = outer.service.intake_git(str(body.get("url", "")), body.get("name"), str(body.get("objective", "")))
                    elif path == "/api/intake/new":
                        result = outer.service.intake_new(body.get("name"), str(body.get("objective", "")))
                    elif path == "/api/intake/sessions":
                        result = outer.service.create_upload_session(body.get("name"), str(body.get("objective", "")), str(body.get("mode", "files")))
                    elif len(parts) == 5 and parts[:3] == ["api", "intake", "sessions"] and parts[4] == "commit":
                        result = outer.service.commit_upload_session(parts[3])
                    elif path == "/api/project":
                        result = outer.service.switch_project(body["path"])
                    elif path == "/api/floors":
                        result = outer.service.switch_project(body["path"])
                    elif path == "/api/add-agent":
                        result = outer.service.add_agent(str(body.get("expertise", "")))
                    elif path.startswith("/api/agents/"):
                        parts = [part for part in path.split("/") if part]
                        if len(parts) == 4 and parts[3] == "steer":
                            result = outer.service.steer_agent(parts[2], str(body.get("message", "")))
                        elif len(parts) == 5 and parts[3] == "control":
                            action = parts[4]
                            if action == "pause":
                                result = outer.service.pause_agent(parts[2])
                            elif action == "resume":
                                result = outer.service.resume_agent(parts[2], bool(body.get("reset_blocked", True)))
                            elif action == "halt":
                                result = outer.service.halt_agent(parts[2])
                            else:
                                raise ValueError("invalid agent control action")
                        else:
                            raise ValueError("invalid agent endpoint")
                    elif path == "/api/start":
                        result = outer.service.start(str(body.get("objective", "")))
                    elif path == "/api/run":
                        mode = body.get("mode")
                        objective = body.get("objective")
                        job_id = outer.jobs.submit("run", lambda: outer.service.run(mode, objective))
                        result = {"job_id": job_id}
                    elif path == "/api/verify":
                        job_id = outer.jobs.submit("verify", outer.service.verify)
                        result = {"job_id": job_id}
                    elif path == "/api/deliver":
                        job_id = outer.jobs.submit("deliver", outer.service.deliver)
                        result = {"job_id": job_id}
                    elif path == "/api/control/pause":
                        result = outer.service.pause()
                    elif path == "/api/control/stop":
                        result = outer.service.stop()
                    elif path == "/api/control/resume":
                        result = outer.service.resume(bool(body.get("reset_blocked", False)))
                    elif path.startswith("/api/approvals/"):
                        parts = [p for p in path.split("/") if p]
                        if len(parts) != 4:
                            raise ValueError("invalid approval endpoint")
                        result = outer.service.decide_approval(parts[2], parts[3])
                    elif path == "/api/objective":
                        result = outer.service.update_objective(str(body.get("objective", "")))
                    elif path == "/api/config":
                        result = outer.service.update_config(body)
                    elif path == "/api/replace-agent":
                        result = outer.service.replace_agent(str(body["old_name"]), str(body["expertise"]))
                    else:
                        self.send_error(404); return
                    self._json(result)
                except KeyError as exc:
                    self._json({"error": "MissingField", "message": str(exc)}, 400)
                except IntakeError as exc:
                    self._json(exc.as_dict(), 400)
                except ValueError as exc:
                    self._json({"error": "ValueError", "message": str(exc)}, 400)
                except Exception as exc:
                    self._json({"error": type(exc).__name__, "message": str(exc)}, 500)

            def do_DELETE(self) -> None:  # noqa: N802
                try:
                    path = unquote(urlparse(self.path).path)
                    parts = [part for part in path.split("/") if part]
                    if len(parts) == 4 and parts[:3] == ["api", "intake", "sessions"]:
                        self._json(outer.service.cancel_upload_session(parts[3]))
                        return
                    self.send_error(404)
                except IntakeError as exc:
                    self._json(exc.as_dict(), 400)
                except Exception as exc:
                    self._json({"error": type(exc).__name__, "message": str(exc)}, 500)

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self.host = host
        self.port = int(self._httpd.server_address[1])

    def serve_forever(self) -> None:
        self._httpd.serve_forever(poll_interval=0.2)

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
