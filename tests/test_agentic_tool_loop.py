from pathlib import Path
import json

from engineering_office.models import Complexity, ProjectState
from engineering_office.models_runtime import ModelRouter, ScriptedProvider
from engineering_office.office import OfficeEngine
from engineering_office.research import ResearchFinding, ResearchManager


def project(root: Path):
    (root/"src").mkdir(); (root/"tests").mkdir(); (root/"src"/"__init__.py").write_text("")
    (root/"src"/"calc.py").write_text("def add(a,b):\n    return a-b\n")
    (root/"tests"/"test_calc.py").write_text("from src.calc import add\ndef test_add(): assert add(2,3)==5\n")
    (root/"pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    (root/"acceptance.json").write_text(json.dumps({"gates":[{"name":"tests","command":"python -m pytest -q","expected_exit":0}],"required_evidence":[]}))


def msg(status, actions=None, research=None, specialists=None, observations=None):
    return json.dumps({"status":status,"observations":observations or ["working"],"interpretations":[],"hypotheses":[],"actions":actions or [],"tests":[],"risks":[],"specialist_requests":specialists or [],"research_requests":research or [],"handoff":""})


def router(provider): return ModelRouter({c:provider for c in Complexity})


def test_diagnostic_tool_output_is_fed_back_before_mutation(tmp_path: Path):
    project(tmp_path)
    provider=ScriptedProvider([
        msg("CONTINUE", actions=[{"tool":"filesystem.read","args":{"path":"src/calc.py"},"reason":"inspect implementation"}], observations=["need source"]),
        msg("COMPLETE", actions=[{"tool":"filesystem.write","args":{"path":"src/calc.py","content":"def add(a,b):\n    return a+b\n"},"reason":"fix wrong operator"}], observations=["source returns a-b"]),
    ])
    engine=OfficeEngine(tmp_path,model_router=router(provider),max_task_iterations=3)
    engine.start("fix")
    result=engine.run()
    assert result["project_state"] == ProjectState.PASS.value
    assert len(provider.calls)==2
    assert "return a-b" in provider.calls[1][1]["content"]


class FakeResearch:
    def research(self, request):
        return [ResearchFinding("Python + performs addition", "python docs", 0.99, "direct", "none")]


def test_research_request_is_resolved_and_fed_back(tmp_path: Path):
    project(tmp_path)
    provider=ScriptedProvider([
        msg("NEEDS_RESEARCH", research=[{"topic":"Python arithmetic","questions":["what does + do?"],"reason":"confirm semantics"}]),
        msg("COMPLETE", actions=[{"tool":"filesystem.write","args":{"path":"src/calc.py","content":"def add(a,b):\n    return a+b\n"},"reason":"apply confirmed semantics"}], observations=["research confirms addition"]),
    ])
    engine=OfficeEngine(tmp_path,model_router=router(provider),research_manager=ResearchManager(FakeResearch()),max_task_iterations=3)
    engine.start("fix")
    result=engine.run()
    assert result["project_state"] == "PASS"
    assert "python docs" in provider.calls[1][1]["content"]


def test_research_request_without_provider_blocks_honestly(tmp_path: Path):
    project(tmp_path)
    provider=ScriptedProvider([msg("NEEDS_RESEARCH", research=[{"topic":"unknown","questions":["x"],"reason":"needed"}])])
    engine=OfficeEngine(tmp_path,model_router=router(provider),max_task_iterations=2)
    engine.start("fix")
    result=engine.run()
    assert result["project_state"] == "BLOCKED"
    assert "research provider" in result["task_results"][0]["reason"].lower()


def test_specialist_request_creates_consultant_and_returns_advice(tmp_path: Path):
    project(tmp_path)
    provider=ScriptedProvider([
        msg("NEEDS_SPECIALIST", specialists=[{"expertise":"Python semantics","reason":"need language specialist"}]),
        msg("COMPLETE", observations=["a-b is wrong for addition"]),
        msg("COMPLETE", actions=[{"tool":"filesystem.write","args":{"path":"src/calc.py","content":"def add(a,b):\n    return a+b\n"},"reason":"use specialist advice"}], observations=["specialist confirmed root cause"]),
    ])
    engine=OfficeEngine(tmp_path,model_router=router(provider),max_task_iterations=4)
    engine.start("fix")
    before=len(list((tmp_path/".office"/"agents").glob("*.json")))
    result=engine.run()
    after=len(list((tmp_path/".office"/"agents").glob("*.json")))
    assert result["project_state"] == "PASS"
    assert after == before + 1
    assert "a-b is wrong" in provider.calls[2][1]["content"]
