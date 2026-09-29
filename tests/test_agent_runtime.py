from pathlib import Path
import json
import pytest

from engineering_office.agent_runtime import AgentProtocolError, AgentRuntime
from engineering_office.models import AgentSpec, Complexity, RiskLevel, TaskContract
from engineering_office.models_runtime import ScriptedProvider
from engineering_office.security import PermissionSet
from engineering_office.tools import FileWriteTool, ToolRegistry


def agent(tools=None):
    return AgentSpec(
        name="Python Specialist", mission="fix python", capabilities=["software_engineering"],
        allowed_tools=tools or ["filesystem.write"], read_scopes=["."], write_scopes=["src"],
        forbidden_actions=["modify acceptance gates"], model_tier=Complexity.MEDIUM,
    )


def task():
    return TaskContract(
        task_id="T1", project_id="P1", goal="fix it", owner="Python Specialist", dependencies=[],
        read_scopes=["."], write_scopes=["src"], required_evidence=["test"],
        acceptance_criteria=["tests pass"], prohibited_actions=["weaken tests"],
        complexity=Complexity.MEDIUM, risk=RiskLevel.LOW,
    )


def response(actions=None):
    return json.dumps({
        "status":"COMPLETE",
        "observations":["test fails"],
        "interpretations":["implementation likely wrong"],
        "hypotheses":[],
        "actions":actions or [],
        "tests":["pytest"],
        "risks":[],
        "specialist_requests":[],
        "research_requests":[],
        "handoff":"verify"
    })


def test_runtime_executes_valid_structured_action(tmp_path: Path):
    (tmp_path / "src").mkdir()
    registry=ToolRegistry(); registry.register(FileWriteTool(tmp_path, PermissionSet(["."],["src"],[])))
    provider=ScriptedProvider([response([{"tool":"filesystem.write","args":{"path":"src/x.txt","content":"ok"},"reason":"implement"}])])
    report=AgentRuntime(provider, registry).run(agent(), task(), {"evidence":["failure"]})
    assert (tmp_path / "src/x.txt").read_text()=="ok"
    assert report.observations == ["test fails"]
    assert report.interpretations == ["implementation likely wrong"]


def test_malformed_json_fails_closed_without_mutation(tmp_path: Path):
    (tmp_path / "src").mkdir()
    registry=ToolRegistry(); registry.register(FileWriteTool(tmp_path, PermissionSet(["."],["src"],[])))
    with pytest.raises(AgentProtocolError):
        AgentRuntime(ScriptedProvider(["not-json"]), registry).run(agent(), task(), {})
    assert list((tmp_path/"src").iterdir()) == []


def test_unknown_tool_prevalidation_prevents_partial_mutation(tmp_path: Path):
    (tmp_path / "src").mkdir()
    registry=ToolRegistry(); registry.register(FileWriteTool(tmp_path, PermissionSet(["."],["src"],[])))
    actions=[
        {"tool":"filesystem.write","args":{"path":"src/x.txt","content":"should-not-write"},"reason":"first"},
        {"tool":"unknown.tool","args":{},"reason":"bad"}
    ]
    with pytest.raises(AgentProtocolError, match="unknown tool"):
        AgentRuntime(ScriptedProvider([response(actions)]), registry).run(agent(tools=["filesystem.write","unknown.tool"]), task(), {})
    assert not (tmp_path / "src/x.txt").exists()


def test_disallowed_tool_is_rejected_before_execution(tmp_path: Path):
    (tmp_path / "src").mkdir()
    registry=ToolRegistry(); registry.register(FileWriteTool(tmp_path, PermissionSet(["."],["src"],[])))
    actions=[{"tool":"filesystem.write","args":{"path":"src/x.txt","content":"no"},"reason":"x"}]
    with pytest.raises(AgentProtocolError, match="not allowed"):
        AgentRuntime(ScriptedProvider([response(actions)]), registry).run(agent(tools=["shell"]), task(), {})
    assert not (tmp_path / "src/x.txt").exists()


def test_missing_observations_or_interpretations_is_invalid(tmp_path: Path):
    registry=ToolRegistry()
    bad=json.dumps({"status":"COMPLETE","observations":[],"hypotheses":[],"actions":[],"tests":[],"risks":[]})
    with pytest.raises(AgentProtocolError, match="interpretations"):
        AgentRuntime(ScriptedProvider([bad]), registry).run(agent(), task(), {})

def test_propose_does_not_execute_until_explicit_execute(tmp_path: Path):
    (tmp_path / "src").mkdir()
    registry=ToolRegistry(); registry.register(FileWriteTool(tmp_path, PermissionSet(["."],["src"],[])))
    provider=ScriptedProvider([response([{"tool":"filesystem.write","args":{"path":"src/x.txt","content":"ok"},"reason":"implement"}])])
    runtime=AgentRuntime(provider, registry)
    rep=runtime.propose(agent(), task(), {})
    assert not (tmp_path / "src/x.txt").exists()
    runtime.execute_actions(agent(), rep)
    assert (tmp_path / "src/x.txt").read_text()=="ok"


def test_execution_trace_preserves_action_args_and_reason(tmp_path: Path):
    (tmp_path / "src").mkdir()
    registry=ToolRegistry(); registry.register(FileWriteTool(tmp_path, PermissionSet(["."],["src"],[])))
    provider=ScriptedProvider([response([{"tool":"filesystem.write","args":{"path":"src/x.txt","content":"ok"},"reason":"implement exact fix"}])])
    report=AgentRuntime(provider, registry).run(agent(), task(), {})
    trace=report.raw["action_results"][0]
    assert trace["args"]["path"] == "src/x.txt"
    assert trace["reason"] == "implement exact fix"
