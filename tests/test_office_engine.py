from pathlib import Path
import json
import pytest

from engineering_office.models import Complexity, ProjectState, TaskState
from engineering_office.models_runtime import ModelRouter, ScriptedProvider
from engineering_office.office import OfficeEngine
from engineering_office.delivery import DeliveryError


def make_project(root: Path):
    (root/"src").mkdir(); (root/"tests").mkdir()
    (root/"pyproject.toml").write_text('[project]\nname="demo"\nversion="0"\n')
    (root/"src"/"__init__.py").write_text("")
    (root/"src"/"calc.py").write_text("def add(a,b):\n    return a-b\n")
    (root/"tests"/"test_calc.py").write_text("from src.calc import add\n\ndef test_add():\n    assert add(2,3)==5\n")
    (root/"acceptance.json").write_text(json.dumps({"gates":[{"name":"tests","command":"python -m pytest -q","expected_exit":0}],"required_evidence":[]}))


def response(content):
    return json.dumps({
        "status":"COMPLETE","observations":["acceptance test fails"],"interpretations":["add implementation is incorrect"],
        "hypotheses":[],"actions":[{"tool":"filesystem.write","args":{"path":"src/calc.py","content":content},"reason":"correct add"}],
        "tests":["pytest -q"],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":"verify"
    })


def uniform_router(provider):
    return ModelRouter({c:provider for c in Complexity})


def test_start_discovers_staffs_plans_and_persists_state(tmp_path: Path):
    make_project(tmp_path)
    engine=OfficeEngine(tmp_path)
    summary=engine.start("fix and finish project")
    assert (tmp_path/".office"/"state.db").exists()
    assert (tmp_path/".office"/"agents").is_dir()
    assert (tmp_path/".office"/"plan.json").exists()
    assert summary["project"]["project_type"] == "software"
    assert any("Software" in a["name"] for a in summary["agents"])
    assert summary["tasks"]


def test_run_repairs_project_then_verifies_and_promotes_memory(tmp_path: Path):
    make_project(tmp_path)
    provider=ScriptedProvider([response("def add(a,b):\n    return a+b\n")])
    engine=OfficeEngine(tmp_path, model_router=uniform_router(provider), max_task_iterations=2)
    start=engine.start("fix project")
    result=engine.run()
    assert result["project_state"] == ProjectState.PASS.value
    assert "return a+b" in (tmp_path/"src"/"calc.py").read_text()
    assert any(m["kind"] == "successful_fix" for m in engine.store.list_memory(start["project"]["project_id"], verified_only=True))
    task_states=[state for _,state in engine.store.list_tasks(start["project"]["project_id"])]
    assert task_states == [TaskState.PASS]


def test_failed_verification_retries_with_feedback(tmp_path: Path):
    make_project(tmp_path)
    provider=ScriptedProvider([
        response("def add(a,b):\n    return a*b\n"),
        response("def add(a,b):\n    return a+b\n"),
    ])
    engine=OfficeEngine(tmp_path, model_router=uniform_router(provider), max_task_iterations=3)
    engine.start("fix project")
    result=engine.run()
    assert result["project_state"] == ProjectState.PASS.value
    assert len(provider.calls) == 2


def test_high_risk_agent_action_blocks_project(tmp_path: Path):
    make_project(tmp_path)
    risky=json.dumps({
        "status":"COMPLETE","observations":["test fails"],"interpretations":["push fix"],"hypotheses":[],
        "actions":[{"tool":"shell","args":{"command":"git push origin main"},"reason":"publish"}],
        "tests":[],"risks":["external"],"specialist_requests":[],"research_requests":[],"handoff":""
    })
    provider=ScriptedProvider([risky])
    engine=OfficeEngine(tmp_path, model_router=uniform_router(provider), max_task_iterations=1)
    engine.start("fix project")
    result=engine.run()
    assert result["project_state"] == ProjectState.BLOCKED.value


def test_delivery_requires_verified_project(tmp_path: Path):
    make_project(tmp_path)
    engine=OfficeEngine(tmp_path)
    engine.start("fix")
    with pytest.raises(DeliveryError):
        engine.deliver()


def test_project_verification_never_routes_to_an_llm(tmp_path: Path):
    make_project(tmp_path)

    class ExplodingRouter:
        def __init__(self): self.calls=0
        def route(self, complexity):
            self.calls += 1
            raise AssertionError("Verifier must not route to an LLM")
        def order_tasks_for_residency(self,tasks): return list(tasks)
        def same_model_batch(self,tasks,limit): return list(tasks)[:limit]

    router=ExplodingRouter()
    engine=OfficeEngine(tmp_path,model_router=router)
    engine.start("verify deterministic gates")
    (tmp_path/"src"/"calc.py").write_text("def add(a,b):\n    return a+b\n")
    report=engine.verify()
    assert report["verdict"] == "PASS"
    assert router.calls == 0
