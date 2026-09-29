import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from engineering_office.models import Complexity
from engineering_office.models_runtime import (
    LocalModelManager,
    LocalModelSpec,
    ModelEndpointConflict,
    ModelOwnershipError,
    ModelRouter,
    ScriptedProvider,
)


class FakeProcess:
    def __init__(self, pid=4321):
        self.pid = pid
        self.terminated = False
        self.killed = False
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def specs(tmp_path: Path):
    return {
        "qwen": LocalModelSpec(
            name="qwen",
            endpoint="http://127.0.0.1:8080/v1",
            expected_model="qwen-30b",
            start_command=["llama-server", "-m", "/models/qwen.gguf", "--port", "8080"],
            startup_timeout=600,
            poll_interval=0.01,
        ),
        "nemotron": LocalModelSpec(
            name="nemotron",
            endpoint="http://127.0.0.1:8081/v1",
            expected_model="nemotron-30b",
            start_command=["llama-server", "-m", "/models/nemotron.gguf", "--port", "8081"],
            startup_timeout=600,
            poll_interval=0.01,
        ),
    }


def test_lifecycle_switch_is_serialized(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    active = 0
    max_active = 0
    guard = threading.Lock()

    def fake_ensure_locked(name):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with guard:
            active -= 1
        return {"name": name, "status": "READY"}

    monkeypatch.setattr(manager, "_ensure_locked", fake_ensure_locked)
    t1 = threading.Thread(target=lambda: manager.ensure("qwen"))
    t2 = threading.Thread(target=lambda: manager.ensure("nemotron"))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert max_active == 1


def test_wrong_model_on_endpoint_fails_without_killing_unknown_process(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    monkeypatch.setattr(manager, "_list_model_ids", lambda spec: ["qwen-1.5b"] if spec.name == "qwen" else [])
    killed = []
    monkeypatch.setattr(manager, "_kill_pid", lambda pid, force=False: killed.append((pid, force)))

    with pytest.raises(ModelEndpointConflict, match="qwen-1.5b"):
        manager.ensure("qwen")
    assert killed == []


def test_stop_refuses_pid_file_when_process_fingerprint_does_not_match(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    meta = manager._pid_metadata(specs(tmp_path)["qwen"], 9876)
    manager._pid_path("qwen").write_text(json.dumps(meta))
    monkeypatch.setattr(manager, "_pid_command_fingerprint", lambda pid: "different-fingerprint")
    killed = []
    monkeypatch.setattr(manager, "_kill_pid", lambda pid, force=False: killed.append((pid, force)))

    with pytest.raises(ModelOwnershipError):
        manager.stop("qwen")
    assert killed == []


def test_ensure_stops_owned_other_model_then_starts_target_and_waits_for_exact_model(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    manager._current_model = "nemotron"
    manager._processes["nemotron"] = FakeProcess(pid=7654)
    order = []
    readiness = {"qwen": [[], ["qwen-30b"]], "nemotron": [["nemotron-30b"]]}

    monkeypatch.setattr(manager, "stop", lambda name: order.append(("stop", name)) or {"name": name, "status": "STOPPED"})
    monkeypatch.setattr(manager, "_spawn", lambda spec: order.append(("start", spec.name)) or FakeProcess())
    monkeypatch.setattr(manager, "_write_pid_record", lambda spec, proc: None)
    monkeypatch.setattr(manager, "_list_model_ids", lambda spec: readiness[spec.name].pop(0) if readiness[spec.name] else [spec.expected_model])
    monkeypatch.setattr("engineering_office.models_runtime.time.sleep", lambda _: None)

    status = manager.ensure("qwen")
    assert order == [("stop", "nemotron"), ("start", "qwen")]
    assert status["status"] == "READY"
    assert status["model_ids"] == ["qwen-30b"]
    assert manager.current_model == "qwen"


def test_router_calls_lifecycle_manager_before_returning_provider(tmp_path: Path):
    class FakeManager:
        current_model = None
        def __init__(self): self.calls = []
        def ensure(self, name): self.calls.append(name); self.current_model = name

    manager = FakeManager()
    qwen = ScriptedProvider(["ok"])
    nemotron = ScriptedProvider(["ok"])
    router = ModelRouter(
        {Complexity.LOW: qwen, Complexity.MEDIUM: qwen, Complexity.HIGH: nemotron, Complexity.ESCALATION: nemotron},
        lifecycle_manager=manager,
        model_bindings={Complexity.LOW:"qwen", Complexity.MEDIUM:"qwen", Complexity.HIGH:"nemotron", Complexity.ESCALATION:"nemotron"},
    )

    assert router.route(Complexity.HIGH) is nemotron
    assert manager.calls == ["nemotron"]


def test_router_orders_ready_tasks_to_keep_current_model_resident():
    class FakeManager:
        current_model = "qwen"
        def ensure(self, name): self.current_model = name

    manager = FakeManager()
    p = ScriptedProvider(["ok"])
    router = ModelRouter(
        {c:p for c in Complexity},
        lifecycle_manager=manager,
        model_bindings={Complexity.LOW:"qwen", Complexity.MEDIUM:"qwen", Complexity.HIGH:"nemotron", Complexity.ESCALATION:"nemotron"},
    )
    tasks = [
        SimpleNamespace(task_id="H1", complexity=Complexity.HIGH),
        SimpleNamespace(task_id="M1", complexity=Complexity.MEDIUM),
        SimpleNamespace(task_id="M2", complexity=Complexity.MEDIUM),
        SimpleNamespace(task_id="H2", complexity=Complexity.HIGH),
    ]
    ordered = router.order_tasks_for_residency(tasks)
    assert [t.task_id for t in ordered] == ["M1", "M2", "H1", "H2"]


def test_router_limits_parallel_batch_to_one_model_family():
    class FakeManager:
        current_model = None
        def ensure(self, name): self.current_model = name

    manager = FakeManager()
    p = ScriptedProvider(["ok"])
    router = ModelRouter(
        {c:p for c in Complexity},
        lifecycle_manager=manager,
        model_bindings={Complexity.LOW:"qwen", Complexity.MEDIUM:"qwen", Complexity.HIGH:"nemotron", Complexity.ESCALATION:"nemotron"},
    )
    tasks = [
        SimpleNamespace(task_id="M1", complexity=Complexity.MEDIUM),
        SimpleNamespace(task_id="H1", complexity=Complexity.HIGH),
        SimpleNamespace(task_id="M2", complexity=Complexity.MEDIUM),
    ]
    batch = router.same_model_batch(tasks, limit=3)
    assert [t.task_id for t in batch] == ["M1", "M2"]


def test_lifecycle_events_include_switch_timestamps(tmp_path: Path, monkeypatch):
    events = []
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime", event_sink=events.append)
    monkeypatch.setattr(manager, "_list_model_ids", lambda spec: [spec.expected_model])
    manager.ensure("qwen")
    assert any(e["event"] == "model.ready" and e["model"] == "qwen" and e.get("timestamp") for e in events)


def test_lifecycle_events_are_persisted_to_jsonl(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    monkeypatch.setattr(manager, "_list_model_ids", lambda spec: [spec.expected_model])
    manager.ensure("qwen")
    log = tmp_path / "runtime" / "lifecycle-events.jsonl"
    assert log.exists()
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert events[-1]["event"] == "model.ready"
    assert events[-1]["model"] == "qwen"


def test_cold_start_validation_requires_empty_endpoints_and_records_sequence(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    monkeypatch.setattr(manager, "stop_all_owned", lambda: [])
    monkeypatch.setattr(manager, "_list_model_ids", lambda spec: [])
    calls=[]
    def fake_ensure(name):
        calls.append(name)
        manager._current_model=name
        return {"name":name,"status":"READY","model_ids":[manager.specs[name].expected_model]}
    monkeypatch.setattr(manager, "_ensure_locked", fake_ensure)
    output=tmp_path/"cold-start.json"
    report=manager.cold_start_validate(["qwen","nemotron","qwen"], output)
    assert calls == ["qwen","nemotron","qwen"]
    assert [r["model"] for r in report["transitions"]] == calls
    assert output.exists()
    saved=json.loads(output.read_text())
    assert saved["cold_start"] is True
    assert saved["final_model"] == "qwen"


def test_cold_start_validation_refuses_preexisting_unowned_endpoint(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    monkeypatch.setattr(manager, "stop_all_owned", lambda: [])
    monkeypatch.setattr(manager, "_list_model_ids", lambda spec: ["qwen-30b"] if spec.name == "qwen" else [])
    with pytest.raises(ModelEndpointConflict, match="cold-start"):
        manager.cold_start_validate(["qwen","nemotron"])


def test_stop_refuses_reused_pid_even_if_command_matches(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    spec = specs(tmp_path)["qwen"]
    fingerprint = manager._command_fingerprint(spec.start_command)
    manager._pid_path("qwen").write_text(json.dumps({
        "pid": 9876,
        "model": "qwen",
        "endpoint": spec.endpoint,
        "expected_model": spec.expected_model,
        "command_fingerprint": fingerprint,
        "process_start_ticks": 111,
    }))
    monkeypatch.setattr(manager, "_pid_command_fingerprint", lambda pid: fingerprint)
    monkeypatch.setattr(manager, "_pid_start_ticks", lambda pid: 222)
    killed=[]
    monkeypatch.setattr(manager, "_kill_pid", lambda pid, force=False: killed.append(pid))
    with pytest.raises(ModelOwnershipError, match="start identity"):
        manager.stop("qwen")
    assert killed == []


def test_switch_refuses_to_start_target_while_other_unowned_model_is_running(tmp_path: Path, monkeypatch):
    manager = LocalModelManager(specs(tmp_path), tmp_path / "runtime")
    def ids(spec):
        if spec.name == "nemotron":
            return ["nemotron-30b"]
        return []
    monkeypatch.setattr(manager, "_list_model_ids", ids)
    spawned=[]
    monkeypatch.setattr(manager, "_spawn", lambda spec: spawned.append(spec.name))
    with pytest.raises(ModelEndpointConflict, match="unowned model"):
        manager.ensure("qwen")
    assert spawned == []
