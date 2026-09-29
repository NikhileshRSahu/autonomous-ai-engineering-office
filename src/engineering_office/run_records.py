from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import uuid

from .runtime_events import RuntimeEventStore, emit_runtime_event


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(slots=True)
class RunStageState:
    name: str
    state: str = "PENDING"
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class RunRecord:
    run_id: str
    project_id: str
    mode: str
    objective: str
    status: str
    started_at_utc: str
    finished_at_utc: str | None
    current_stage: str | None
    stage_started_at_utc: str | None
    stages: list[RunStageState] = field(default_factory=list)
    report_dir: str | None = None
    model_strategy: str | None = None
    index_generation: int | None = None
    needs_user_count: int = 0
    result_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RunRecord":
        data = dict(raw)
        data["stages"] = [RunStageState(**row) for row in data.get("stages", [])]
        return cls(**data)


class RunRecordStore:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.runs_dir = self.root / ".office" / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: RunRecord) -> RunRecord:
        target = self.runs_dir / record.run_id / "run.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(target)
        return record

    def load(self, run_id: str) -> RunRecord:
        return RunRecord.from_dict(json.loads((self.runs_dir / run_id / "run.json").read_text(encoding="utf-8")))

    def list(self) -> list[RunRecord]:
        rows: list[RunRecord] = []
        for path in self.runs_dir.glob("*/run.json"):
            try:
                rows.append(RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return sorted(rows, key=lambda row: row.started_at_utc)

    def latest_active(self, project_id: str | None = None) -> RunRecord | None:
        active = [row for row in self.list() if row.finished_at_utc is None and (project_id is None or row.project_id == project_id)]
        return active[-1] if active else None

    def latest(self, project_id: str | None = None) -> RunRecord | None:
        rows = [row for row in self.list() if project_id is None or row.project_id == project_id]
        return rows[-1] if rows else None


class RunCoordinator:
    def __init__(
        self,
        project_root: str | Path,
        *,
        project_id: str,
        event_store: RuntimeEventStore | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.root = Path(project_root).resolve()
        self.project_id = project_id
        self.store = RunRecordStore(self.root)
        self.events = event_store
        self._now_fn = now_fn or _utcnow
        self._active: RunRecord | None = self.store.latest_active(project_id)

    def _now(self) -> datetime:
        value = self._now_fn()
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    def start(self, mode: str, objective: str, stages: list[str]) -> RunRecord:
        if not stages:
            raise ValueError("run must define at least one stage")
        now = self._now()
        stamp = now.strftime("%Y%m%d-%H%M%S")
        run_id = f"RUN-{stamp}-{uuid.uuid4().hex[:6]}"
        stage_rows = [RunStageState(name=str(name).upper()) for name in stages]
        stage_rows[0].state = "RUNNING"
        stage_rows[0].started_at_utc = now.isoformat()
        record = RunRecord(
            run_id=run_id,
            project_id=self.project_id,
            mode=str(mode),
            objective=str(objective),
            status="RUNNING",
            started_at_utc=now.isoformat(),
            finished_at_utc=None,
            current_stage=stage_rows[0].name,
            stage_started_at_utc=now.isoformat(),
            stages=stage_rows,
            report_dir=str(self.root / ".office" / "reports" / run_id),
        )
        self._active = self.store.save(record)
        self._emit("run.started", f"Run {run_id} started", {"run_id": run_id, "mode": mode, "stage": record.current_stage})
        return record

    def active(self) -> RunRecord:
        if self._active is None:
            self._active = self.store.latest_active(self.project_id) or self.store.latest(self.project_id)
        if self._active is None:
            raise RuntimeError("no run record exists")
        return self._active

    def transition(self, stage: str, state: str, detail: str | None = None) -> RunRecord:
        record = self.active()
        if record.finished_at_utc is not None:
            return record
        stage = str(stage).upper()
        state = str(state).upper()
        now = self._now().isoformat()
        target = next((row for row in record.stages if row.name == stage), None)
        if target is None:
            raise ValueError(f"unknown run stage: {stage}")
        current = next((row for row in record.stages if row.name == record.current_stage), None)
        if current is not None and current is not target and current.state == "RUNNING":
            current.state = "PASS"
            current.finished_at_utc = now
        if target.started_at_utc is None:
            target.started_at_utc = now
        target.state = state
        target.detail = detail
        if state in {"PASS", "WARN", "BLOCKED", "SKIPPED", "FAILED"}:
            target.finished_at_utc = target.finished_at_utc or now
        if state == "RUNNING" or record.current_stage != stage:
            record.current_stage = stage
            record.stage_started_at_utc = target.started_at_utc or now
        record = self.store.save(record)
        self._active = record
        self._emit("run.stage_changed", f"{stage}: {state}", {"run_id": record.run_id, "stage": stage, "state": state, "detail": detail})
        return record

    def finish(self, status: str, summary: dict[str, Any] | None = None) -> RunRecord:
        record = self.active()
        if record.finished_at_utc is not None:
            return record
        now = self._now().isoformat()
        current = next((row for row in record.stages if row.name == record.current_stage), None)
        if current is not None and current.state == "RUNNING":
            current.state = "PASS" if str(status).upper() in {"PASS", "AUDIT_COMPLETE"} else str(status).upper()
            current.finished_at_utc = now
        record.status = str(status).upper()
        record.finished_at_utc = now
        record.result_summary = dict(summary or {})
        record = self.store.save(record)
        self._active = record
        self._emit("run.finished", f"Run {record.run_id} finished: {record.status}", {"run_id": record.run_id, "status": record.status, "summary": record.result_summary})
        return record

    def timing(self, now: datetime | None = None) -> dict[str, Any]:
        record = self.active()
        start = _parse(record.started_at_utc)
        end = _parse(record.finished_at_utc) or now or self._now()
        stage_start = _parse(record.stage_started_at_utc) or start
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return {
            "run_id": record.run_id,
            "status": record.status,
            "current_stage": record.current_stage,
            "total_elapsed_seconds": max(0.0, (end - start).total_seconds()) if start else 0.0,
            "stage_elapsed_seconds": max(0.0, (end - stage_start).total_seconds()) if stage_start else 0.0,
            "started_at_utc": record.started_at_utc,
            "finished_at_utc": record.finished_at_utc,
        }

    def _emit(self, kind: str, summary: str, payload: dict[str, Any]) -> None:
        if self.events is None:
            return
        emit_runtime_event(self.events, project_id=self.project_id, kind=kind, summary=summary, payload=payload, source="run")
