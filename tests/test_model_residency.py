from __future__ import annotations

from pathlib import Path
import threading
import time

import pytest


class FakeLocal:
    def __init__(self):
        self.current_model=None
        self.calls=[]
        self.states={"qwen":"STOPPED","nemotron":"STOPPED"}
        self.specs={"qwen":object(),"nemotron":object()}
    def status(self,name): return {"name":name,"status":self.states[name],"owned":True}
    def ensure(self,name):
        self.calls.append(("ensure",name)); self.current_model=name; self.states[name]="READY"; return {"name":name,"status":"READY","path":"cold"}
    def stop(self,name):
        self.calls.append(("stop",name)); self.states[name]="STOPPED"; self.current_model=None if self.current_model==name else self.current_model; return {"name":name,"status":"STOPPED"}
    def _emit(self,event,model,**payload): self.calls.append((event,model,payload))


def test_ready_model_is_reused_without_cold_load(tmp_path: Path):
    from engineering_office.models_runtime import ModelResidencyManager, ResidencyState
    local=FakeLocal(); local.states["qwen"]="READY"; local.current_model="qwen"
    mgr=ModelResidencyManager(local)
    out=mgr.ensure("qwen")
    assert out["residency"] == ResidencyState.GPU_READY.value
    assert not [c for c in local.calls if c[:2]==("ensure","qwen")]


def test_sleeping_model_wakes_before_cold_load():
    from engineering_office.models_runtime import ModelResidencyManager, ResidencyState
    local=FakeLocal(); calls=[]
    mgr=ModelResidencyManager(local, sleep_hooks={"qwen":lambda: calls.append("sleep")}, wake_hooks={"qwen":lambda: calls.append("wake") or {"status":"READY"}})
    mgr._states["qwen"]=ResidencyState.CPU_RESIDENT
    out=mgr.ensure("qwen")
    assert calls == ["wake"]
    assert out["residency"] == ResidencyState.GPU_READY.value
    assert not [c for c in local.calls if c[:2]==("ensure","qwen")]


def test_memory_guard_can_block_cold_load():
    from engineering_office.models_runtime import ModelResidencyManager, ModelLifecycleError
    local=FakeLocal(); mgr=ModelResidencyManager(local, memory_guard=lambda name: False)
    with pytest.raises(ModelLifecycleError, match="memory guard"):
        mgr.ensure("qwen")


def test_sleep_uses_hook_and_marks_cpu_resident():
    from engineering_office.models_runtime import ModelResidencyManager, ResidencyState
    local=FakeLocal(); local.states["qwen"]="READY"; local.current_model="qwen"; calls=[]
    mgr=ModelResidencyManager(local, sleep_hooks={"qwen":lambda: calls.append("sleep")})
    out=mgr.sleep("qwen")
    assert calls == ["sleep"]
    assert out["residency"] == ResidencyState.CPU_RESIDENT.value


def test_no_sleep_hook_stops_owned_model_safely():
    from engineering_office.models_runtime import ModelResidencyManager, ResidencyState
    local=FakeLocal(); local.states["qwen"]="READY"; local.current_model="qwen"
    mgr=ModelResidencyManager(local)
    out=mgr.sleep("qwen")
    assert ("stop","qwen") in local.calls
    assert out["residency"] == ResidencyState.COLD.value


def test_concurrent_ensure_is_serialized():
    from engineering_office.models_runtime import ModelResidencyManager
    class Slow(FakeLocal):
        def ensure(self,name):
            self.calls.append(("begin",name)); time.sleep(.03); self.calls.append(("end",name)); self.current_model=name; self.states[name]="READY"; return {"name":name,"status":"READY"}
    local=Slow(); mgr=ModelResidencyManager(local)
    ts=[threading.Thread(target=lambda n=n:mgr.ensure(n)) for n in ["qwen","nemotron"]]
    [t.start() for t in ts]; [t.join() for t in ts]
    seq=[x[:2] for x in local.calls if x[0] in {"begin","end"}]
    assert seq in [[("begin","qwen"),("end","qwen"),("begin","nemotron"),("end","nemotron")],[ ("begin","nemotron"),("end","nemotron"),("begin","qwen"),("end","qwen")]]
