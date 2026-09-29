import json
import pytest
from engineering_office.agent_factory import AgentFactory
from engineering_office.capabilities import CapabilityRegistry
from engineering_office.discovery import ProjectDiscovery
from engineering_office.model_planning import ModelPlanGenerator, PlanGenerationError
from engineering_office.models_runtime import ScriptedProvider


def setup_project(tmp_path):
    (tmp_path/"frontend").mkdir(); (tmp_path/"backend").mkdir()
    (tmp_path/"package.json").write_text(json.dumps({"dependencies":{"react":"1","express":"1"}}))
    project=ProjectDiscovery().inspect(tmp_path,"finish app")
    agents=AgentFactory(CapabilityRegistry.default()).staff(project)
    return project, agents


def valid_plan():
    return json.dumps({"tasks":[
        {"task_id":"T-FE","goal":"finish frontend","owner":"Frontend Engineer","dependencies":[],"write_scopes":["frontend"],"required_evidence":["ui-test"],"acceptance_criteria":["ui gate"],"prohibited_actions":[],"complexity":"LOW","risk":"LOW","gates":[{"name":"ui","command":"python -c \"print('ui')\"","expected_exit":0}]},
        {"task_id":"T-BE","goal":"finish backend","owner":"Backend Engineer","dependencies":[],"write_scopes":["backend"],"required_evidence":["api-test"],"acceptance_criteria":["api gate"],"prohibited_actions":[],"complexity":"HIGH","risk":"MEDIUM","gates":[{"name":"api","command":"python -c \"print('api')\"","expected_exit":0}]}
    ]})


def test_model_plan_generator_creates_valid_multi_specialist_plan(tmp_path):
    project,agents=setup_project(tmp_path)
    plan=ModelPlanGenerator(ScriptedProvider([valid_plan()])).generate(project,agents)
    assert {t.owner for t in plan.tasks} == {"Frontend Engineer","Backend Engineer"}
    assert plan.tasks[0].metadata["gates"][0]["name"] == "ui"


def test_model_plan_rejects_unknown_owner(tmp_path):
    project,agents=setup_project(tmp_path)
    raw=json.loads(valid_plan()); raw["tasks"][0]["owner"]="Imaginary Expert"
    with pytest.raises(PlanGenerationError,match="owner"):
        ModelPlanGenerator(ScriptedProvider([json.dumps(raw)])).generate(project,agents)


def test_model_plan_rejects_write_scope_outside_agent_authority(tmp_path):
    project,agents=setup_project(tmp_path)
    raw=json.loads(valid_plan()); raw["tasks"][0]["write_scopes"]=["backend"]
    with pytest.raises(PlanGenerationError,match="write scope"):
        ModelPlanGenerator(ScriptedProvider([json.dumps(raw)])).generate(project,agents)


def test_model_plan_rejects_cycle(tmp_path):
    project,agents=setup_project(tmp_path)
    raw=json.loads(valid_plan()); raw["tasks"][0]["dependencies"]=["T-BE"]; raw["tasks"][1]["dependencies"]=["T-FE"]
    with pytest.raises(ValueError,match="cycle"):
        ModelPlanGenerator(ScriptedProvider([json.dumps(raw)])).generate(project,agents)
