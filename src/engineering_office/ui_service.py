from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
import json
import threading
import time
import uuid
import subprocess

from .config import OfficeConfig
from .floor_registry import FloorRegistry
from .intake import IntakeResult, IntakeSessionManager, UniversalIntakeService
from .models import dataclass_to_jsonable
from .office import OfficeEngine
from .routing import build_model_router
from .run_records import RunCoordinator, RunRecordStore
from .project_index import ProjectIndex
from .eta import EtaEstimator
from .providers import OpenRouterClient, GeminiClient, GroqClient


class JobManager:
    """Small in-process job registry used by the local UI.

    Office execution can take minutes.  HTTP requests therefore enqueue work and
    the dashboard polls this registry instead of blocking the web server.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, fn: Callable[[], Any]) -> str:
        job_id = f"JOB-{uuid.uuid4().hex[:10]}"
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "name": name,
                "state": "RUNNING",
                "created_at": time.time(),
                "finished_at": None,
                "result": None,
                "error": None,
            }

        def worker() -> None:
            try:
                result = fn()
            except Exception as exc:  # surfaced to the UI rather than swallowed
                with self._lock:
                    self._jobs[job_id].update(
                        state="FAIL",
                        error={"type": type(exc).__name__, "message": str(exc)},
                        finished_at=time.time(),
                    )
            else:
                with self._lock:
                    self._jobs[job_id].update(state="PASS", result=result, finished_at=time.time())

        threading.Thread(target=worker, daemon=True, name=f"office-ui-{job_id}").start()
        return job_id

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return dict(self._jobs[job_id])

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in sorted(self._jobs.values(), key=lambda x: x["created_at"], reverse=True)]


class DashboardService:
    """Application boundary for the local control-room UI.

    The service never reimplements engineering authority.  Mutations are routed
    through OfficeEngine/ApprovalManager/OfficeControl so the GUI has exactly
    the same safety and verification semantics as the CLI.
    """

    def __init__(
        self,
        project_root: str | Path,
        floor_registry_path: str | Path | None = None,
        intake_workspace_root: str | Path | None = None,
        intake_staging_root: str | Path | None = None,
        intake_max_files: int = 100_000,
        intake_max_bytes: int = 8 * 1024 * 1024 * 1024,
        intake_session_ttl: int = 24 * 60 * 60,
    ):
        self.root = self._validate_root(project_root)
        self.floors = FloorRegistry(floor_registry_path)
        self.floors.touch(self.root)
        self.intake = UniversalIntakeService(
            workspace_root=intake_workspace_root,
            staging_root=intake_staging_root,
            max_files=intake_max_files,
            max_uncompressed_bytes=intake_max_bytes,
        )
        self.intake_sessions = IntakeSessionManager(self.intake, session_ttl_seconds=intake_session_ttl)
        self._engine: OfficeEngine | None = None

    @staticmethod
    def _validate_root(path: str | Path) -> Path:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"project root is not a directory: {root}")
        return root

    @property
    def initialized(self) -> bool:
        return (self.root / ".office" / "project.json").is_file()

    @property
    def engine(self) -> OfficeEngine:
        if self._engine is None:
            config_path = self.root / ".office" / "config.json"
            router = None
            kwargs: dict[str, Any] = {}
            try:
                cfg = OfficeConfig.load(config_path) if config_path.is_file() else OfficeConfig()
                router = build_model_router(config_path if config_path.is_file() else None, project_root=self.root)
                kwargs = {
                    "max_task_iterations": cfg.max_task_iterations,
                    "parallelism": cfg.parallelism,
                    "max_feedback_cycles": cfg.max_feedback_cycles,
                }
            except Exception:
                # Keep the control room usable so the configuration can be corrected in Settings.
                router = None
            self._engine = OfficeEngine(self.root, model_router=router, **kwargs)
        return self._engine

    @staticmethod
    def _intake_payload(result: IntakeResult, initialized: bool) -> dict[str, Any]:
        return {
            "root": str(result.root),
            "project_root": str(result.root),
            "source": str(result.source),
            "kind": result.kind.value,
            "managed": result.managed,
            "extracted_files": result.extracted_files,
            "bytes_materialized": result.bytes_materialized,
            "detected_root": str(result.detected_root or result.root),
            "warnings": list(result.warnings),
            "initialized": initialized,
        }

    def _activate_intake(self, result: IntakeResult) -> dict[str, Any]:
        root = self._validate_root(result.root)
        source = str(result.source)
        source_name = Path(source).name if result.kind.value != "git" else source
        self.root = root
        self._engine = None
        self.floors.touch(root, {
            "source_kind": result.kind.value,
            "source_name": source_name,
            "managed": bool(result.managed),
        })
        return self._intake_payload(result, self.initialized)

    def intake_path(self, path: str | Path, objective: str = "") -> dict[str, Any]:
        return self._activate_intake(self.intake.from_path(path, objective=objective))

    def intake_files(self, paths: list[str | Path], objective: str = "", name: str | None = None) -> dict[str, Any]:
        return self._activate_intake(self.intake.from_files(paths, objective=objective, display_name=name))

    def intake_paste(self, name: str | None, objective: str, items: list[dict[str, str]]) -> dict[str, Any]:
        return self._activate_intake(self.intake.from_paste(name=name, objective=objective, items=items))

    def intake_git(self, url: str, name: str | None = None, objective: str = "") -> dict[str, Any]:
        return self._activate_intake(self.intake.from_git(url=url, name=name, objective=objective))

    def intake_new(self, name: str | None, objective: str) -> dict[str, Any]:
        return self._activate_intake(self.intake.from_new(name=name, objective=objective))

    def create_upload_session(self, display_name: str | None = None, objective: str = "", mode: str = "files") -> dict[str, Any]:
        return self.intake_sessions.create(display_name=display_name, objective=objective, mode=mode)

    def upload_session_file(self, session_id: str, relative_path: str, data, size: int | None = None) -> dict[str, Any]:
        return self.intake_sessions.upload(session_id, relative_path, data, size=size)

    def commit_upload_session(self, session_id: str) -> dict[str, Any]:
        return self._activate_intake(self.intake_sessions.commit(session_id))

    def cancel_upload_session(self, session_id: str) -> dict[str, Any]:
        return self.intake_sessions.cancel(session_id)

    def switch_project(self, project_root: str | Path) -> dict[str, Any]:
        self.root = self._validate_root(project_root)
        self.floors.touch(self.root)
        self._engine = None
        return self.snapshot()

    def list_floors(self) -> list[dict[str, Any]]:
        self.floors.touch(self.root)
        return self.floors.list(current=self.root)

    def start(self, objective: str) -> dict[str, Any]:
        if not objective.strip():
            raise ValueError("objective must be non-empty")
        result = self.engine.start(objective.strip())
        config_path = self.root / ".office" / "config.json"
        if not config_path.exists():
            config_path.write_text(json.dumps({
                "model_profiles": {}, "routing": {}, "max_feedback_cycles": 4,
                "max_task_iterations": 6, "parallelism": 2,
                "intake_workspace_root": "~/.engineering-office/workspaces",
                "intake_staging_root": "~/.engineering-office/staging",
                "intake_max_files": 100_000,
                "intake_max_bytes": 8 * 1024 * 1024 * 1024,
                "intake_session_ttl": 24 * 60 * 60,
            }, indent=2))
        return result

    def update_config(self, raw: dict[str, Any]) -> dict[str, Any]:
        office_dir = self.root / ".office"
        office_dir.mkdir(parents=True, exist_ok=True)
        target = office_dir / "config.json"
        temp = office_dir / "config.json.tmp"
        temp.write_text(json.dumps(raw, indent=2, sort_keys=True))
        try:
            cfg = OfficeConfig.load(temp)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        temp.replace(target)
        self._engine = None
        return self._read_config(target)

    def run(self, mode: str | None = None, objective: str | None = None) -> dict[str, Any]:
        config_path = self.root / ".office" / "config.json"
        cfg = OfficeConfig.load(config_path) if config_path.is_file() else OfficeConfig()
        selected_mode = mode or cfg.default_run_mode
        if objective and self.initialized:
            self.engine.update_objective(objective)
        return self.engine.run_mode(
            selected_mode, objective,
            max_context_files=cfg.fast_audit_max_context_files,
            max_context_chars=cfg.fast_audit_max_context_chars,
        )

    def verify(self) -> dict[str, Any]:
        return self.engine.verify()

    def deliver(self) -> dict[str, Any]:
        path = self.engine.deliver()
        return {"path": path}

    def pause(self) -> dict[str, Any]:
        self.engine.pause()
        return self.engine.control.state()

    def stop(self) -> dict[str, Any]:
        self.engine.stop()
        return self.engine.control.state()

    def resume(self, reset_blocked: bool = False) -> dict[str, Any]:
        self.engine.resume(reset_blocked=reset_blocked)
        return self.engine.control.state()

    def pause_agent(self, agent_name: str) -> dict[str, Any]:
        return self.engine.pause_agent(agent_name)

    def halt_agent(self, agent_name: str) -> dict[str, Any]:
        return self.engine.halt_agent(agent_name)

    def resume_agent(self, agent_name: str, reset_blocked: bool = True) -> dict[str, Any]:
        return self.engine.resume_agent(agent_name, reset_blocked=reset_blocked)

    def steer_agent(self, agent_name: str, message: str) -> dict[str, Any]:
        return self.engine.steer_agent(agent_name, message)

    def add_agent(self, expertise: str) -> dict[str, Any]:
        return dataclass_to_jsonable(self.engine.add_agent(expertise))

    def _safe_runtime_payload(self, value: Any) -> Any:
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key in {"path", "file", "cwd"} and isinstance(item, str):
                    candidate = Path(item)
                    if candidate.is_absolute():
                        try:
                            item = str(candidate.resolve().relative_to(self.root))
                        except Exception:
                            continue
                out[key] = self._safe_runtime_payload(item)
            return out
        if isinstance(value, list):
            return [self._safe_runtime_payload(item) for item in value]
        return value

    def events(self, after: str | None = None, agent_id: str | None = None, task_id: str | None = None, limit: int = 500) -> dict[str, Any]:
        if not self.initialized:
            return {"events": [], "cursor": after, "diagnostics": []}
        rows = self.engine.runtime_events.read(after=after, agent_id=agent_id, task_id=task_id, limit=max(1, min(int(limit), 2000)))
        events = []
        for event in rows:
            raw = event.to_dict()
            raw["payload"] = self._safe_runtime_payload(raw.get("payload") or {})
            events.append(raw)
        return {
            "events": events,
            "cursor": events[-1]["id"] if events else after,
            "diagnostics": list(self.engine.runtime_events.diagnostics[-20:]),
        }

    def recent_events(self, limit: int = 250) -> dict[str, Any]:
        if not self.initialized:
            return {"events": [], "cursor": None, "diagnostics": []}
        rows = self.engine.runtime_events.recent(max(1, min(int(limit), 1000)))
        events = []
        for event in rows:
            raw = event.to_dict(); raw["payload"] = self._safe_runtime_payload(raw.get("payload") or {}); events.append(raw)
        return {"events": events, "cursor": events[-1]["id"] if events else None, "diagnostics": list(self.engine.runtime_events.diagnostics[-20:])}

    @staticmethod
    def _event_text(event: dict[str, Any]) -> tuple[str, bool]:
        kind = event.get("kind", "event")
        payload = event.get("payload") or {}
        summary = str(event.get("summary") or kind)
        truncated = False
        if kind == "command.started":
            return f"$ {payload.get('command') or summary}", False
        if kind == "command.output":
            text = "\n".join(part for part in [str(payload.get("stdout") or "").rstrip(), str(payload.get("stderr") or "").rstrip()] if part)
            if len(text) > 12000:
                text = text[-12000:]
                truncated = True
            return text or summary, truncated
        if kind == "command.finished":
            return f"[{payload.get('returncode', '?')}] {payload.get('command') or 'command finished'}", False
        if kind in {"file.read", "file.written", "file.diff_available"}:
            return f"{kind}: {payload.get('path') or summary}", False
        if kind == "message.sent":
            return f"message: {payload.get('sender', '?')} → {payload.get('recipient', '?')}: {summary}", False
        if kind.startswith("model."):
            return f"model: {summary}", False
        if kind.startswith("verification."):
            return f"verifier: {summary}", False
        return summary, False

    def agent_terminal(self, agent_id: str, after: str | None = None, limit: int = 300) -> dict[str, Any]:
        payload = self.events(after=after, agent_id=agent_id, limit=limit)
        entries=[]
        for event in payload["events"]:
            text, truncated = self._event_text(event)
            entries.append({
                "id": event["id"], "timestamp": event["timestamp"], "kind": event["kind"],
                "phase": event["phase"], "text": text, "truncated": truncated,
                "severity": event["severity"], "task_id": event.get("task_id"),
                "payload": event.get("payload") or {},
            })
        return {"agent_id": agent_id, "entries": entries, "cursor": payload["cursor"], "diagnostics": payload["diagnostics"]}

    def agent_activity(self, agent_id: str) -> dict[str, Any]:
        payload = self.events(agent_id=agent_id, limit=1000)
        latest = payload["events"][-1] if payload["events"] else None
        phase = latest["phase"] if latest else "IDLE"
        location_map = {
            "DISCOVERING": "intake", "PLANNING": "director", "READING": "engineering", "CODING": "engineering",
            "RUNNING_COMMAND": "engineering", "TESTING": "lab", "RESEARCHING": "research", "EXPERIMENTING": "lab",
            "MESSAGING": "review", "REVIEWING": "review", "VERIFYING": "verification", "MODEL_LOADING": "models",
            "NEEDS_USER": "director", "BLOCKED": "waiting", "FAILED": "waiting", "VERIFIED": "verification",
            "PAUSED": "waiting", "HALTED": "waiting", "WAITING": "break", "IDLE": "break",
        }
        return {"agent_id": agent_id, "phase": phase, "location": location_map.get(phase, "break"), "event": latest}

    def models_runtime(self) -> dict[str, Any]:
        payload = self.events(limit=2000)
        models: dict[str, Any] = {}
        for event in payload["events"]:
            if not str(event.get("kind", "")).startswith("model."):
                continue
            data = event.get("payload") or {}
            model = str(data.get("model") or data.get("name") or event.get("summary", "model").split(":", 1)[0])
            models[model] = {"phase": event.get("phase"), "kind": event.get("kind"), "timestamp": event.get("timestamp"), "payload": data}
        return {"models": models}

    def replay_events(self, start: str | None, end: str | None, agent_id: str | None = None, task_id: str | None = None, limit: int = 5000) -> dict[str, Any]:
        if not self.initialized:
            return {"events": [], "diagnostics": []}
        rows = self.engine.runtime_events.read(agent_id=agent_id, task_id=task_id, limit=min(max(1, int(limit)), 50_000))
        events=[]
        for event in rows:
            if start and event.timestamp < start:
                continue
            if end and event.timestamp > end:
                continue
            raw=event.to_dict(); raw["payload"]=self._safe_runtime_payload(raw.get("payload") or {}); events.append(raw)
        return {"events": events, "diagnostics": list(self.engine.runtime_events.diagnostics[-50:]), "start": start, "end": end}

    def timeline(self, *, agent_id: str | None = None, task_id: str | None = None, category: str | None = None, limit: int = 500) -> dict[str, Any]:
        payload=self.events(agent_id=agent_id, task_id=task_id, limit=min(max(1,int(limit)),2000))
        category=(category or "").lower().strip()
        if category:
            def keep(event):
                kind=str(event.get("kind","")).lower(); severity=str(event.get("severity","")).lower()
                if category=="model": return kind.startswith("model.")
                if category=="review": return kind.startswith("review.") or "review" in kind
                if category=="verification": return kind.startswith("verification.")
                if category=="error": return severity=="error" or event.get("phase") in {"FAILED","BLOCKED"}
                if category=="agent": return bool(event.get("agent_id"))
                if category=="task": return bool(event.get("task_id"))
                return category in kind
            payload["events"]=[e for e in payload["events"] if keep(e)]
            payload["cursor"]=payload["events"][-1]["id"] if payload["events"] else None
        return payload

    def agent_detail(self, agent_name: str) -> dict[str, Any]:
        if not self.initialized:
            raise RuntimeError("office is not initialized")
        status = self.engine.status()
        project_id = status["project_id"]
        tasks = status.get("tasks", [])
        if agent_name == "Office Director":
            agent = {
                "name": "Office Director", "role": "orchestrator", "mission": "Coordinate the office, route work and protect verification boundaries.",
                "capabilities": ["orchestration", "planning", "governance"], "model_tier": "HIGH", "write_scopes": [], "allowed_tools": [],
            }
            task_row = None
            task_id = None
            control = {"state": "running"}
        else:
            agent = next((item for item in status.get("agents", []) if item.get("name") == agent_name), None)
            if agent is None:
                raise KeyError(agent_name)
            owned = [row for row in tasks if row.get("task", {}).get("owner") == agent_name]
            task_row = next((row for row in owned if row.get("state") not in {"PASS", "FAILED", "BLOCKED"}), owned[-1] if owned else None)
            task_id = task_row.get("task", {}).get("task_id") if task_row else None
            control = self.engine.agent_control.state(agent_name)

        all_messages = self.engine.store.list_messages(project_id)
        messages = [m for m in all_messages if m.get("sender") == agent_name or m.get("recipient") == agent_name or (agent_name == "Office Director" and (m.get("sender") == "Office Director" or m.get("recipient") == "Office Director"))]
        queue = [m for m in messages if m.get("recipient") == agent_name]
        all_events = self.engine.store.list_events(project_id)
        if agent_name == "Office Director":
            traces = all_events[-250:]
        else:
            traces = [event for event in all_events if event.get("task_id") == task_id or event.get("data", {}).get("agent") == agent_name][-250:]
        evidence_refs = self.engine.evidence.list_refs(project_id, task_id) if task_id else []
        evidence = [dataclass_to_jsonable(ref) for ref in evidence_refs]
        return {
            "agent": agent,
            "control": control,
            "task": task_row,
            "terminal": [entry["text"] for entry in self.agent_terminal(agent_name, limit=500)["entries"]] or self._terminal_lines(agent_name, task_id, evidence_refs, traces),
            "files": self._agent_files(agent),
            "messages": messages[-250:],
            "queue": queue[-100:],
            "evidence": evidence,
            "traces": traces,
        }

    def _terminal_lines(self, agent_name: str, task_id: str | None, evidence_refs: list[Any], traces: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for ref in evidence_refs:
            if ref.name != "execution.json":
                continue
            try:
                actions = json.loads(Path(ref.path).read_text())
            except Exception:
                continue
            if not isinstance(actions, list):
                continue
            for action in actions:
                if not isinstance(action, dict):
                    continue
                tool = str(action.get("tool", "tool"))
                args = action.get("args") or {}
                command = args.get("command") if isinstance(args, dict) else None
                if command:
                    lines.append(f"$ {command}")
                elif tool.startswith("filesystem.") and isinstance(args, dict) and args.get("path"):
                    lines.append(f"› {tool} {args.get('path')}")
                else:
                    lines.append(f"› {tool}")
                reason = str(action.get("reason", "")).strip()
                if reason:
                    lines.append(f"# {reason}")
                stdout = str(action.get("stdout", "")).rstrip()
                stderr = str(action.get("stderr", "")).rstrip()
                if stdout:
                    lines.extend(stdout.splitlines()[-80:])
                if stderr:
                    lines.extend(f"! {line}" for line in stderr.splitlines()[-40:])
                lines.append(f"[{action.get('returncode', 0)}] {'ok' if action.get('ok') else 'failed'}")
        if not lines:
            label = task_id or "office"
            lines.append(f"Engineering Office · {agent_name}")
            lines.append(f"session: {label}")
            for event in traces[-20:]:
                data = event.get("data") or {}
                detail = data.get("reason") or data.get("state") or data.get("message") or ""
                lines.append(f"{event.get('kind', 'event')}: {detail}".rstrip())
        return lines[-500:]

    def _agent_files(self, agent: dict[str, Any]) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        try:
            proc = subprocess.run(["git", "status", "--short"], cwd=self.root, capture_output=True, text=True, timeout=4)
        except Exception:
            proc = None
        if proc is not None and proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if len(line) < 4:
                    continue
                files.append({"status": line[:2].strip() or "M", "path": line[3:].strip()})
        if not files:
            for scope in agent.get("write_scopes", []) if isinstance(agent, dict) else []:
                if scope:
                    files.append({"status": "scope", "path": str(scope)})
        return files[:250]

    def current_run(self) -> dict[str, Any] | None:
        record = RunRecordStore(self.root).latest()
        return record.to_dict() if record is not None else None

    def run_timing(self) -> dict[str, Any]:
        record = RunRecordStore(self.root).latest()
        if record is None:
            return {"state":"NONE","total_elapsed_seconds":0,"stage_elapsed_seconds":0,"eta":{"state":"LEARNING","lower_seconds":None,"upper_seconds":None,"sample_count":0,"label":"Learning from this run…"}}
        coordinator = RunCoordinator(self.root, project_id=record.project_id)
        timing = coordinator.timing()
        project = self._read_json(self.root / ".office" / "project.json", {})
        residency = self.models_residency().get("models", {}) if self.initialized else {}
        statuses = {str(row.get("status") or row.get("state") or row.get("phase") or "").upper() for row in residency.values() if isinstance(row, dict)}
        warm_states = {"READY","GPU_READY","CPU_RESIDENT","SLEEPING","BUSY"}
        model_state = "warm" if statuses & warm_states else "cold"
        features = {
            "project_type": project.get("project_type") or "unknown",
            "model_state": model_state,
            "simulation_level": "none" if record.mode in {"fast-audit", "check-report"} else "project",
            "runtime_strategy": record.model_strategy or "default",
        }
        timing["eta"] = EtaEstimator(self.root).estimate(record, features).to_dict()
        return timing

    def run_report(self) -> dict[str, Any]:
        record = RunRecordStore(self.root).latest()
        if record is None:
            return {"available":False}
        report_dir = self.root / ".office" / "reports" / record.run_id
        report = report_dir / "REPORT.md"
        summary = report_dir / "SUMMARY.html"
        return {
            "available": report.is_file(),
            "run_id": record.run_id,
            "status": record.status,
            "path": f"reports/{record.run_id}/REPORT.md" if report.is_file() else None,
            "summary_path": f"reports/{record.run_id}/SUMMARY.html" if summary.is_file() else None,
            "directory": str(report_dir),
        }

    def provider_status(self) -> dict[str, Any]:
        import os
        router = getattr(getattr(self, "engine", None), "model_router", None) if self.initialized else None
        manager = getattr(router, "lifecycle_manager", None) if router is not None else None
        local_models = sorted(getattr(manager, "specs", {}).keys()) if manager is not None else []
        local_configured = bool(local_models)
        if router is not None and not local_configured:
            local_configured = any(
                getattr(provider, "local_provider", None) is not None
                for provider in getattr(router, "providers", {}).values()
            )

        # Status is configuration-only and never performs a network call.
        # It deliberately distinguishes an API key being present from the
        # provider being eligible under the strict zero-cost policy.
        cloud_clients = {
            "openrouter": OpenRouterClient(),
            "gemini": GeminiClient(),
            "groq": GroqClient(),
        }
        cloud = {name: client.status() for name, client in cloud_clients.items()}
        eligible = any(row.get("configured") and row.get("zero_cost_eligible") for row in cloud.values())
        configured = any(row.get("configured") for row in cloud.values())
        mode = "hybrid" if eligible else ("cloud-needs-confirmation" if configured else "local")
        return {
            "mode": mode,
            "privacy": "sanitized-evidence-only",
            "zero_cost_only": True,
            "local": {"configured": local_configured, "models": local_models},
            "cloud": cloud,
        }

    def index_status(self) -> dict[str, Any]:
        return ProjectIndex(self.root).status()

    def models_residency(self) -> dict[str, Any]:
        models: dict[str, Any] = {}
        if self.initialized:
            manager = getattr(getattr(self.engine, "model_router", None), "lifecycle_manager", None)
            if manager is not None:
                for name in getattr(manager, "specs", {}):
                    try: models[name] = manager.status(name)
                    except Exception as exc: models[name] = {"name":name,"status":"ERROR","message":str(exc)}
        if not models:
            models = self.models_runtime().get("models", {}) if self.initialized else {}
        return {"models":models}

    def needs_user(self) -> dict[str, Any]:
        items=[]
        if self.initialized:
            items=[asdict(x) for x in self.engine.approvals.list("PENDING")]
            events=self.events(limit=500).get("events",[])
            for event in events:
                if event.get("phase") == "NEEDS_USER" and event.get("kind") != "approval.requested":
                    items.append({"type":"event","summary":event.get("summary"),"event_id":event.get("id")})
        return {"count":len(items),"items":items}

    def update_objective(self, objective: str) -> dict[str, Any]:
        return dataclass_to_jsonable(self.engine.update_objective(objective))

    def replace_agent(self, old_name: str, expertise: str) -> dict[str, Any]:
        return dataclass_to_jsonable(self.engine.replace_agent(old_name, expertise))

    def decide_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
        if decision == "approve":
            item = self.engine.approvals.approve(approval_id)
        elif decision == "deny":
            item = self.engine.approvals.deny(approval_id)
        else:
            raise ValueError("decision must be approve or deny")
        return asdict(item)

    def snapshot(self) -> dict[str, Any]:
        office_dir = self.root / ".office"
        base: dict[str, Any] = {
            "project_root": str(self.root),
            "project_name": self.root.name,
            "initialized": self.initialized,
            "control": self._read_json(office_dir / "control.json", {"paused": False, "stopped": False}),
            "approvals": self._read_json(office_dir / "approvals.json", []),
            "config": self._read_config(office_dir / "config.json"),
            "delivery": self._list_delivery(office_dir / "delivery"),
            "jobs": [],
            "floors": self.list_floors(),
            "agent_controls": self.engine.agent_control.all_states() if self.initialized else {},
        }
        if not self.initialized:
            return base | {
                "status": None,
                "events": [],
                "messages": [],
                "memory": [],
                "evidence": [],
                "decisions": [],
                "agent_metrics": {},
            }

        engine = self.engine
        status = engine.status()
        project_id = status["project_id"]
        metrics = {agent["name"]: engine.store.get_agent_metrics(agent["name"]) for agent in status["agents"]}
        return base | {
            "status": status,
            "events": engine.store.list_events(project_id),
            "messages": engine.store.list_messages(project_id),
            "memory": engine.store.list_memory(project_id),
            "evidence": [dataclass_to_jsonable(x) for x in engine.evidence.list_refs(project_id)],
            "decisions": [dataclass_to_jsonable(x) for x in engine.decisions.list()],
            "agent_metrics": metrics,
        }

    def office_file(self, relative_path: str) -> tuple[bytes, str]:
        """Read a UI-safe artifact under `.office/evidence` or `.office/delivery`."""
        rel = Path(relative_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("invalid office artifact path")
        office = (self.root / ".office").resolve()
        allowed = [(office / "evidence").resolve(), (office / "delivery").resolve(), (office / "reports").resolve()]
        target = (office / rel).resolve()
        if not any(target == base or base in target.parents for base in allowed):
            raise ValueError("artifact is outside evidence/delivery/reports scope")
        if not target.is_file():
            raise FileNotFoundError(relative_path)
        suffix = target.suffix.lower()
        content_type = {
            ".json": "application/json; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
            ".txt": "text/plain; charset=utf-8",
            ".log": "text/plain; charset=utf-8",
            ".html": "text/html; charset=utf-8",
        }.get(suffix, "application/octet-stream")
        return target.read_bytes(), content_type

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _read_config(path: Path) -> dict[str, Any]:
        cfg = OfficeConfig()
        if path.is_file():
            try:
                raw = json.loads(path.read_text())
                raw.setdefault("intake_workspace_root", cfg.intake_workspace_root)
                raw.setdefault("intake_staging_root", cfg.intake_staging_root)
                raw.setdefault("intake_max_files", cfg.intake_max_files)
                raw.setdefault("intake_max_bytes", cfg.intake_max_bytes)
                raw.setdefault("intake_session_ttl", cfg.intake_session_ttl)
                return raw
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "model_profiles": {},
            "routing": {},
            "max_feedback_cycles": cfg.max_feedback_cycles,
            "max_task_iterations": cfg.max_task_iterations,
            "parallelism": cfg.parallelism,
            "intake_workspace_root": cfg.intake_workspace_root,
            "intake_staging_root": cfg.intake_staging_root,
            "intake_max_files": cfg.intake_max_files,
            "intake_max_bytes": cfg.intake_max_bytes,
            "intake_session_ttl": cfg.intake_session_ttl,
        }

    @staticmethod
    def _list_delivery(path: Path) -> list[dict[str, Any]]:
        if not path.is_dir():
            return []
        out = []
        for file in sorted(path.rglob("*")):
            if file.is_file():
                out.append({"name": file.name, "path": str(file.relative_to(path.parent)), "size": file.stat().st_size})
        return out
