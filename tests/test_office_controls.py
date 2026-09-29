from pathlib import Path
import json
from engineering_office.models import Complexity
from engineering_office.models_runtime import ModelRouter, ScriptedProvider
from engineering_office.office import OfficeEngine


def router(p): return ModelRouter({c:p for c in Complexity})

def make_project(root: Path, acceptance=None):
    (root/"src").mkdir(); (root/"src"/"__init__.py").write_text("")
    (root/"pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    if acceptance is None: acceptance={"gates":[{"name":"gate","command":"python -c \"raise SystemExit(1)\"","expected_exit":0}],"required_evidence":[]}
    (root/"acceptance.json").write_text(json.dumps(acceptance))

def msg(actions):
    return json.dumps({"status":"COMPLETE","observations":["gate fails"],"interpretations":[],"hypotheses":[],"actions":actions,"tests":[],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":""})


def test_pause_prevents_model_execution_until_resume(tmp_path: Path):
    make_project(tmp_path)
    p=ScriptedProvider([msg([])])
    e=OfficeEngine(tmp_path,model_router=router(p),max_task_iterations=1)
    e.start("fix")
    e.pause()
    result=e.run()
    assert result["control"] == "PAUSED"
    assert len(p.calls)==0
    e.resume()
    e.run()
    assert len(p.calls)==1


def test_risky_action_creates_approval_then_can_resume(tmp_path: Path):
    (tmp_path/"scratch").mkdir()
    gate={"gates":[{"name":"scratch-removed","command":"python -c \"import pathlib,sys; sys.exit(0 if not pathlib.Path('scratch').exists() else 1)\"","expected_exit":0}],"required_evidence":[]}
    make_project(tmp_path,gate)
    action=[{"tool":"shell","args":{"command":"rm -rf scratch"},"reason":"remove generated scratch as requested"}]
    p=ScriptedProvider([msg(action),msg(action)])
    e=OfficeEngine(tmp_path,model_router=router(p),max_task_iterations=2)
    e.start("remove scratch and verify")
    first=e.run()
    assert first["project_state"] == "BLOCKED"
    pending=e.approvals.list("PENDING")
    assert len(pending)==1 and pending[0].risk_class=="destructive"
    e.approvals.approve(pending[0].approval_id)
    e.resume(reset_blocked=True)
    second=e.run()
    assert second["project_state"] == "PASS"
    assert not (tmp_path/"scratch").exists()


def test_replace_agent_updates_task_owner(tmp_path: Path):
    make_project(tmp_path)
    e=OfficeEngine(tmp_path); start=e.start("fix")
    old=start["tasks"][0]["owner"]
    new=e.replace_agent(old,"Python Debugging")
    plan=json.loads((tmp_path/".office"/"plan.json").read_text())
    assert plan["tasks"][0]["owner"] == new.name
    assert any("Python Debugging" in p.read_text() for p in (tmp_path/".office"/"agents").glob("*.json"))


def test_update_objective_is_persisted(tmp_path: Path):
    make_project(tmp_path)
    e=OfficeEngine(tmp_path); e.start("old")
    e.update_objective("new objective")
    assert e.status()["objective"] == "new objective"
