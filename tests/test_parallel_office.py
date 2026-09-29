from pathlib import Path
import json
from engineering_office.models import Complexity, ProjectState
from engineering_office.models_runtime import ModelRouter, ScriptedProvider
from engineering_office.office import OfficeEngine


def report(path, content):
    return json.dumps({"status":"COMPLETE","observations":["task gate fails"],"interpretations":["missing deliverable"],"hypotheses":[],"actions":[{"tool":"filesystem.write","args":{"path":path,"content":content},"reason":"create required deliverable"}],"tests":[],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":"verify"})


def plan_json():
    return json.dumps({"tasks":[
        {"task_id":"T-FE","goal":"frontend deliverable","owner":"Frontend Engineer","dependencies":[],"write_scopes":["frontend"],"required_evidence":[],"acceptance_criteria":["frontend done"],"prohibited_actions":[],"complexity":"LOW","risk":"LOW","gates":[{"name":"frontend","command":"python -c \"import pathlib,sys; sys.exit(0 if pathlib.Path('frontend/done.txt').exists() else 1)\"","expected_exit":0}]},
        {"task_id":"T-BE","goal":"backend deliverable","owner":"Backend Engineer","dependencies":[],"write_scopes":["backend"],"required_evidence":[],"acceptance_criteria":["backend done"],"prohibited_actions":[],"complexity":"HIGH","risk":"LOW","gates":[{"name":"backend","command":"python -c \"import pathlib,sys; sys.exit(0 if pathlib.Path('backend/done.txt').exists() else 1)\"","expected_exit":0}]}
    ]})


def test_office_executes_disjoint_specialists_with_task_specific_gates(tmp_path: Path):
    (tmp_path/"frontend").mkdir(); (tmp_path/"backend").mkdir()
    (tmp_path/"package.json").write_text(json.dumps({"dependencies":{"react":"1","express":"1"}}))
    low=ScriptedProvider([report("frontend/done.txt","frontend complete")])
    high=ScriptedProvider([report("backend/done.txt","backend complete")])
    router=ModelRouter({Complexity.LOW:low, Complexity.MEDIUM:low, Complexity.HIGH:high, Complexity.ESCALATION:high})
    engine=OfficeEngine(tmp_path,model_router=router,parallelism=2)
    engine.start("complete both frontend and backend")
    planner=ScriptedProvider([plan_json()])
    engine.plan_with_model(planner)
    result=engine.run()
    assert result["project_state"] == ProjectState.PASS.value
    assert (tmp_path/"frontend/done.txt").exists()
    assert (tmp_path/"backend/done.txt").exists()
    assert len(low.calls)==1 and len(high.calls)==1


def test_office_uses_model_residency_batching_when_lifecycle_router_is_configured(tmp_path: Path):
    (tmp_path/"frontend").mkdir(); (tmp_path/"backend").mkdir()
    (tmp_path/"package.json").write_text(json.dumps({"dependencies":{"react":"1","express":"1"}}))

    class Manager:
        current_model = "qwen"
        def __init__(self): self.ensure_calls=[]
        def ensure(self, name): self.ensure_calls.append(name); self.current_model=name

    manager=Manager()
    low=ScriptedProvider([report("frontend/done.txt","frontend complete")])
    high=ScriptedProvider([report("backend/done.txt","backend complete")])
    router=ModelRouter(
        {Complexity.LOW:low, Complexity.MEDIUM:low, Complexity.HIGH:high, Complexity.ESCALATION:high},
        lifecycle_manager=manager,
        model_bindings={Complexity.LOW:"qwen", Complexity.MEDIUM:"qwen", Complexity.HIGH:"nemotron", Complexity.ESCALATION:"nemotron"},
    )
    residency_calls=[]
    original=router.same_model_batch
    def traced(tasks, limit):
        selected=original(tasks,limit)
        residency_calls.append([t.task_id for t in selected])
        return selected
    router.same_model_batch=traced

    engine=OfficeEngine(tmp_path,model_router=router,parallelism=2)
    engine.start("complete both frontend and backend")
    engine.plan_with_model(ScriptedProvider([plan_json()]))
    result=engine.run()

    assert result["project_state"] == ProjectState.PASS.value
    assert residency_calls[0] == ["T-FE"]
    assert manager.ensure_calls == ["qwen", "nemotron"]
