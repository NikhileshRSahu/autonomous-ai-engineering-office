from pathlib import Path
import pytest

from engineering_office.models import (
    AgentSpec, Complexity, ProjectMap, ProjectState, RiskLevel,
    TaskContract, TaskState, Verdict, legal_task_transition,
)
from engineering_office.storage import OfficeStore


def test_task_transition_rejects_illegal_jump():
    assert legal_task_transition(TaskState.NEW, TaskState.TRIAGED)
    assert not legal_task_transition(TaskState.NEW, TaskState.PASS)


def test_store_round_trips_project_task_event_and_memory(tmp_path: Path):
    store = OfficeStore(tmp_path / "office.db")
    project = ProjectMap(
        project_id="P1", root=str(tmp_path), objective="finish it",
        project_type="python", technologies=["Python"], working_components=[],
        broken_components=["tests"], constraints=[], risk_areas=[],
        required_domains=["software_engineering"], unknowns=[]
    )
    store.upsert_project(project, ProjectState.PROJECT_MAPPED)
    task = TaskContract(
        task_id="T1", project_id="P1", goal="fix test", owner="python_engineer",
        dependencies=[], read_scopes=["."], write_scopes=["src"],
        required_evidence=["test-output"], acceptance_criteria=["pytest passes"],
        prohibited_actions=["weaken tests"], complexity=Complexity.MEDIUM,
        risk=RiskLevel.LOW
    )
    store.upsert_task(task, TaskState.ASSIGNED)
    store.add_event("P1", "T1", "task.assigned", {"owner": "python_engineer"})
    memory_id = store.add_memory("P1", "rejected_approach", {"idea": "hide failure"}, verified=False)

    loaded_project = store.get_project("P1")
    loaded_task = store.get_task("T1")
    events = store.list_events("P1")
    memory = store.get_memory(memory_id)

    assert loaded_project.project_type == "python"
    assert loaded_task.complexity is Complexity.MEDIUM
    assert events[-1]["kind"] == "task.assigned"
    assert memory["verified"] is False


def test_store_updates_agent_metrics(tmp_path: Path):
    store = OfficeStore(tmp_path / "office.db")
    store.record_agent_outcome("db_specialist", verified_success=True, false_pass=False, iterations=2)
    store.record_agent_outcome("db_specialist", verified_success=False, false_pass=True, iterations=4)
    metrics = store.get_agent_metrics("db_specialist")
    assert metrics["tasks"] == 2
    assert metrics["verified_successes"] == 1
    assert metrics["false_passes"] == 1
    assert metrics["average_iterations"] == 3.0


def test_agent_spec_rejects_empty_mission():
    with pytest.raises(ValueError):
        AgentSpec(
            name="x", mission="", capabilities=["software_engineering"],
            allowed_tools=["filesystem.read"], read_scopes=["."], write_scopes=[],
            forbidden_actions=[], model_tier=Complexity.LOW,
        )
