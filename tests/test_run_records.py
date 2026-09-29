from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pytest


def test_run_record_unique_ids_and_persistence(tmp_path: Path):
    from engineering_office.run_records import RunCoordinator
    from engineering_office.runtime_events import RuntimeEventStore

    events = RuntimeEventStore(tmp_path)
    a = RunCoordinator(tmp_path, project_id="P-1", event_store=events).start("fast-audit", "audit", ["IMPORT", "INDEX", "REPORT"])
    b = RunCoordinator(tmp_path, project_id="P-1", event_store=events).start("fast-audit", "audit", ["IMPORT", "INDEX", "REPORT"])
    assert a.run_id != b.run_id
    saved = json.loads((tmp_path / ".office" / "runs" / a.run_id / "run.json").read_text())
    assert saved["run_id"] == a.run_id
    assert saved["current_stage"] == "IMPORT"
    assert [row["name"] for row in saved["stages"]] == ["IMPORT", "INDEX", "REPORT"]


def test_stage_transition_resets_stage_timer_and_freezes_finish(tmp_path: Path):
    from engineering_office.run_records import RunCoordinator

    base = datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc)
    clock = [base]
    rc = RunCoordinator(tmp_path, project_id="P-1", now_fn=lambda: clock[0])
    record = rc.start("check-report", "inspect", ["IMPORT", "INDEX", "REPORT"])
    clock[0] += timedelta(seconds=30)
    timing = rc.timing()
    assert timing["total_elapsed_seconds"] == pytest.approx(30)
    assert timing["stage_elapsed_seconds"] == pytest.approx(30)

    rc.transition("INDEX", "RUNNING", "hashing")
    clock[0] += timedelta(seconds=12)
    timing = rc.timing()
    assert timing["total_elapsed_seconds"] == pytest.approx(42)
    assert timing["stage_elapsed_seconds"] == pytest.approx(12)

    finished = rc.finish("BLOCKED", {"reason": "model unavailable"})
    frozen = rc.timing()
    clock[0] += timedelta(hours=2)
    assert rc.timing() == frozen
    assert finished.status == "BLOCKED"
    assert finished.finished_at_utc is not None
    assert finished.result_summary["reason"] == "model unavailable"


def test_transition_updates_stage_history(tmp_path: Path):
    from engineering_office.run_records import RunCoordinator

    rc = RunCoordinator(tmp_path, project_id="P-1")
    rc.start("fast-audit", "inspect", ["IMPORT", "INDEX", "ANALYZE", "REPORT"])
    rc.transition("IMPORT", "PASS")
    rc.transition("INDEX", "RUNNING")
    record = rc.active()
    states = {row.name: row.state for row in record.stages}
    assert states["IMPORT"] == "PASS"
    assert states["INDEX"] == "RUNNING"
    assert record.current_stage == "INDEX"


def test_run_events_are_emitted(tmp_path: Path):
    from engineering_office.run_records import RunCoordinator
    from engineering_office.runtime_events import RuntimeEventStore

    store = RuntimeEventStore(tmp_path)
    rc = RunCoordinator(tmp_path, project_id="P-9", event_store=store)
    rc.start("fast-audit", "inspect", ["IMPORT", "REPORT"])
    rc.transition("IMPORT", "PASS")
    rc.transition("REPORT", "RUNNING")
    rc.finish("AUDIT_COMPLETE")
    kinds = [event.kind for event in store.read(limit=100)]
    assert "run.started" in kinds
    assert "run.stage_changed" in kinds
    assert "run.finished" in kinds


def test_active_returns_latest_unfinished_run_after_restart(tmp_path: Path):
    from engineering_office.run_records import RunCoordinator

    first = RunCoordinator(tmp_path, project_id="P-1")
    active = first.start("fast-audit", "inspect", ["IMPORT", "REPORT"])
    recovered = RunCoordinator(tmp_path, project_id="P-1")
    assert recovered.active().run_id == active.run_id
    assert recovered.timing()["total_elapsed_seconds"] >= 0
