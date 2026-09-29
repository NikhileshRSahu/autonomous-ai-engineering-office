from __future__ import annotations

import json
from pathlib import Path

from engineering_office.agent_control import AgentControlManager
from engineering_office.communications import MessageKind
from engineering_office.models import TaskState
from engineering_office.office import OfficeEngine


def make_project(root: Path) -> Path:
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("VALUE = 1\n")
    (root / "acceptance.json").write_text(json.dumps({"gates": [], "required_evidence": []}))
    return root


def test_agent_control_manager_persists_pause_halt_resume(tmp_path: Path):
    manager = AgentControlManager(tmp_path / "agent_controls.json")
    assert manager.state("Agent A")["state"] == "running"
    manager.pause("Agent A")
    assert AgentControlManager(tmp_path / "agent_controls.json").state("Agent A")["state"] == "paused"
    manager.halt("Agent A")
    assert manager.state("Agent A")["state"] == "halted"
    manager.resume("Agent A")
    assert manager.state("Agent A")["state"] == "running"


def test_engine_steer_persists_message_for_agent(tmp_path: Path):
    project = make_project(tmp_path / "p")
    engine = OfficeEngine(project)
    started = engine.start("Complete")
    agent = started["agents"][0]["name"]

    result = engine.steer_agent(agent, "Check the failing test before editing.")

    assert result["recipient"] == agent
    messages = engine.store.list_messages(started["project"]["project_id"])
    steer = messages[-1]
    assert steer["sender"] == "User"
    assert steer["recipient"] == agent
    assert steer["kind"] == MessageKind.STEER.value
    assert steer["data"]["message"] == "Check the failing test before editing."


def test_paused_agent_blocks_owned_task_and_resume_requeues_it(tmp_path: Path):
    project = make_project(tmp_path / "p")
    engine = OfficeEngine(project)
    started = engine.start("Complete")
    agent = started["agents"][0]["name"]
    task_id = started["tasks"][0]["task_id"]

    engine.pause_agent(agent)
    result = engine.run()

    assert result["project_state"] == "BLOCKED"
    assert engine.store.get_task_state(task_id) is TaskState.BLOCKED
    assert "paused" in result["task_results"][0]["reason"]

    engine.resume_agent(agent, reset_blocked=True)
    assert engine.store.get_task_state(task_id) is TaskState.ASSIGNED
    assert engine.agent_control.state(agent)["state"] == "running"


def test_halted_agent_blocks_owned_task(tmp_path: Path):
    project = make_project(tmp_path / "p")
    engine = OfficeEngine(project)
    started = engine.start("Complete")
    agent = started["agents"][0]["name"]

    engine.halt_agent(agent)
    result = engine.run()

    assert result["project_state"] == "BLOCKED"
    assert "halted" in result["task_results"][0]["reason"]


def test_steer_message_is_injected_into_agent_model_context(tmp_path: Path):
    from engineering_office.models import Complexity
    from engineering_office.models_runtime import ModelRouter, ScriptedProvider

    project = tmp_path / "p"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "calc.py").write_text("def add(a,b):\n    return a-b\n")
    (project / "test_calc.py").write_text("from src.calc import add\n\ndef test_add():\n    assert add(2,3)==5\n")
    (project / "acceptance.json").write_text(json.dumps({"gates": [{"name": "tests", "command": "python -m pytest -q", "expected_exit": 0}], "required_evidence": []}))
    fixed = json.dumps({
        "status": "COMPLETE",
        "observations": ["test fails"],
        "interpretations": ["implementation is wrong"],
        "hypotheses": [],
        "actions": [{"tool": "filesystem.write", "args": {"path": "src/calc.py", "content": "def add(a,b):\\n    return a+b\\n"}, "reason": "fix"}],
        "tests": ["pytest -q"], "risks": [], "specialist_requests": [], "research_requests": [], "handoff": "verify"
    })
    provider = ScriptedProvider([fixed])
    router = ModelRouter({level: provider for level in Complexity})
    engine = OfficeEngine(project, model_router=router)
    started = engine.start("Fix")
    agent = started["agents"][0]["name"]
    engine.steer_agent(agent, "Inspect the failing test first.")

    engine.run()

    serialized = json.dumps(provider.calls[0])
    assert "Inspect the failing test first." in serialized
