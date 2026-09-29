from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import threading
import uuid

from .security import redact_runtime_value


_PHASES = {
    "project.discovered": "DISCOVERING",
    "project.staffed": "PLANNING",
    "project.planned": "PLANNING",
    "task.started": "PLANNING",
    "task.state_changed": "PLANNING",
    "agent.selected_model": "WAITING",
    "agent.steered": "WAITING",
    "tool.started": "RUNNING_COMMAND",
    "tool.finished": "WAITING",
    "file.read": "READING",
    "file.written": "CODING",
    "file.diff_available": "CODING",
    "command.started": "RUNNING_COMMAND",
    "command.output": "RUNNING_COMMAND",
    "command.finished": "WAITING",
    "test.started": "TESTING",
    "test.finished": "WAITING",
    "research.started": "RESEARCHING",
    "research.finished": "WAITING",
    "message.sent": "MESSAGING",
    "message.received": "MESSAGING",
    "review.started": "REVIEWING",
    "review.finished": "WAITING",
    "hypothesis.recorded": "READING",
    "hypothesis.rejected": "REVIEWING",
    "verification.started": "VERIFYING",
    "approval.requested": "NEEDS_USER",
    "approval.resolved": "WAITING",
    "model.starting": "MODEL_LOADING",
    "model.loading": "MODEL_LOADING",
    "model.ready": "WAITING",
    "model.busy": "WAITING",
    "model.stopping": "MODEL_LOADING",
    "model.stopped": "WAITING",
    "model.error": "BLOCKED",
    "project.blocked": "BLOCKED",
    "project.delivered": "VERIFIED",
}


def normalize_phase(kind: str, payload: dict[str, Any] | None = None) -> str:
    payload = payload or {}
    if kind == "verification.finished":
        status = str(payload.get("status") or payload.get("state") or "").upper()
        if status == "PASS":
            return "VERIFIED"
        if status in {"FAIL", "FAILED", "ERROR"}:
            return "FAILED"
        return "WAITING"
    return _PHASES.get(kind, "IDLE")


@dataclass(slots=True)
class RuntimeEvent:
    id: str
    timestamp: str
    project_id: str
    agent_id: str | None
    task_id: str | None
    kind: str
    phase: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"
    source: str = "office"
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RuntimeEvent":
        required = {
            "id", "timestamp", "project_id", "agent_id", "task_id", "kind",
            "phase", "summary", "payload", "severity", "source", "correlation_id",
        }
        if not required.issubset(raw):
            missing = sorted(required.difference(raw))
            raise ValueError(f"runtime event missing fields: {missing}")
        return cls(**{key: raw[key] for key in required})


class RuntimeEventStore:
    def __init__(self, project_root: str | Path, max_events: int = 50_000):
        self.project_root = Path(project_root).resolve()
        self.path = self.project_root / ".office" / "runtime" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_events = max(1, int(max_events))
        self._lock = threading.Lock()
        self.diagnostics: list[dict[str, Any]] = []

    def append(self, event: RuntimeEvent) -> RuntimeEvent:
        safe = RuntimeEvent(
            id=event.id,
            timestamp=event.timestamp,
            project_id=event.project_id,
            agent_id=event.agent_id,
            task_id=event.task_id,
            kind=event.kind,
            phase=event.phase,
            summary=str(redact_runtime_value(event.summary)),
            payload=redact_runtime_value(event.payload),
            severity=event.severity,
            source=event.source,
            correlation_id=event.correlation_id,
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(safe.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
        return safe

    def read(
        self,
        after: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        limit: int = 1000,
    ) -> list[RuntimeEvent]:
        if not self.path.exists():
            return []
        result: list[RuntimeEvent] = []
        seen_after = after is None
        self.diagnostics = []
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = RuntimeEvent.from_dict(json.loads(line))
                except Exception as exc:
                    self.diagnostics.append({
                        "kind": "malformed_runtime_event",
                        "line": line_no,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    })
                    continue
                if not seen_after:
                    if event.id == after:
                        seen_after = True
                    continue
                if after is not None and event.id == after:
                    continue
                if agent_id is not None and event.agent_id != agent_id:
                    continue
                if task_id is not None and event.task_id != task_id:
                    continue
                result.append(event)
                if len(result) >= max(1, int(limit)):
                    break
        return result

    def recent(self, limit: int = 100) -> list[RuntimeEvent]:
        events = self.read(limit=self.max_events)
        return events[-max(0, int(limit)):] if limit else []


def emit_runtime_event(
    store: RuntimeEventStore,
    *,
    project_id: str,
    kind: str,
    summary: str,
    agent_id: str | None = None,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
    severity: str = "info",
    source: str = "office",
    correlation_id: str | None = None,
    timestamp: str | None = None,
) -> RuntimeEvent:
    safe_payload = redact_runtime_value(payload or {})
    event = RuntimeEvent(
        id=f"EV-{uuid.uuid4().hex[:16]}",
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        project_id=str(project_id),
        agent_id=agent_id,
        task_id=task_id,
        kind=str(kind),
        phase=normalize_phase(str(kind), safe_payload),
        summary=str(redact_runtime_value(summary)),
        payload=safe_payload,
        severity=str(severity),
        source=str(source),
        correlation_id=correlation_id,
    )
    return store.append(event)
