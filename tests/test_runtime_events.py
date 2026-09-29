from __future__ import annotations

import json
from pathlib import Path

import pytest

from engineering_office.runtime_events import RuntimeEvent, RuntimeEventStore, emit_runtime_event, normalize_phase


def test_runtime_event_has_stable_contract(tmp_path: Path):
    store = RuntimeEventStore(tmp_path)
    event = emit_runtime_event(
        store,
        project_id="P-1",
        agent_id="agent-a",
        task_id="T-1",
        kind="file.read",
        summary="Read src/main.py",
        payload={"path": "src/main.py"},
        source="tool",
        correlation_id="C-1",
    )
    data = event.to_dict()
    assert set(data) == {
        "id", "timestamp", "project_id", "agent_id", "task_id", "kind",
        "phase", "summary", "payload", "severity", "source", "correlation_id",
    }
    assert event.phase == "READING"
    assert event.id.startswith("EV-")


@pytest.mark.parametrize(
    ("kind", "payload", "expected"),
    [
        ("file.read", {}, "READING"),
        ("file.written", {}, "CODING"),
        ("command.started", {}, "RUNNING_COMMAND"),
        ("test.started", {}, "TESTING"),
        ("review.started", {}, "REVIEWING"),
        ("verification.started", {}, "VERIFYING"),
        ("model.loading", {}, "MODEL_LOADING"),
        ("verification.finished", {"status": "PASS"}, "VERIFIED"),
        ("verification.finished", {"status": "FAIL"}, "FAILED"),
        ("totally.unknown", {}, "IDLE"),
    ],
)
def test_normalize_phase_is_deterministic(kind: str, payload: dict, expected: str):
    assert normalize_phase(kind, payload) == expected


def test_unknown_event_can_never_create_success_state():
    assert normalize_phase("future.successish", {"status": "PASS"}) == "IDLE"


def test_payload_and_summary_are_redacted_before_persistence(tmp_path: Path):
    store = RuntimeEventStore(tmp_path)
    event = emit_runtime_event(
        store,
        project_id="P-1",
        kind="command.started",
        summary="using api_key=super-secret-value",
        payload={"command": "curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz' x", "nested": {"token": "token=very-secret"}},
        source="tool",
    )
    raw = store.path.read_text()
    assert "super-secret-value" not in raw
    assert "abcdefghijklmnopqrstuvwxyz" not in raw
    assert "very-secret" not in raw
    assert "REDACTED" in raw
    assert "super-secret-value" not in event.summary


def test_malformed_jsonl_is_skipped_and_diagnostic_is_recorded(tmp_path: Path):
    store = RuntimeEventStore(tmp_path)
    emit_runtime_event(store, project_id="P", kind="project.discovered", summary="ok")
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write("{broken json\n")
    events = store.read()
    assert len(events) == 1
    assert events[0].kind == "project.discovered"
    assert store.diagnostics
    assert store.diagnostics[-1]["kind"] == "malformed_runtime_event"


def test_incremental_read_after_event_id(tmp_path: Path):
    store = RuntimeEventStore(tmp_path)
    first = emit_runtime_event(store, project_id="P", kind="task.started", summary="one", agent_id="a")
    second = emit_runtime_event(store, project_id="P", kind="file.read", summary="two", agent_id="a")
    third = emit_runtime_event(store, project_id="P", kind="file.written", summary="three", agent_id="b")
    assert [event.id for event in store.read(after=first.id)] == [second.id, third.id]
    assert [event.id for event in store.read(after=first.id, agent_id="a")] == [second.id]
    assert store.read(after=third.id) == []


def test_recent_is_bounded(tmp_path: Path):
    store = RuntimeEventStore(tmp_path)
    for i in range(5):
        emit_runtime_event(store, project_id="P", kind="task.started", summary=str(i))
    assert [e.summary for e in store.recent(2)] == ["3", "4"]
