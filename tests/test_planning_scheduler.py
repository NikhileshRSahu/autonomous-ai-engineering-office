import pytest
from engineering_office.models import Complexity, RiskLevel, TaskContract, TaskState
from engineering_office.planning import ProjectPlan, PlanValidator
from engineering_office.scheduler import Scheduler, WriteLockManager


def task(tid, deps=None, writes=None):
    return TaskContract(
        task_id=tid, project_id="P1", goal=tid, owner="agent", dependencies=deps or [],
        read_scopes=["."], write_scopes=writes or [], required_evidence=[], acceptance_criteria=[],
        prohibited_actions=[], complexity=Complexity.LOW, risk=RiskLevel.LOW,
    )


def test_validator_rejects_cycle():
    plan = ProjectPlan([task("A", ["B"]), task("B", ["A"])])
    with pytest.raises(ValueError, match="cycle"):
        PlanValidator.validate(plan)


def test_scheduler_returns_only_ready_non_terminal_tasks():
    plan = ProjectPlan([task("A"), task("B", ["A"]), task("C")])
    states = {"A": TaskState.PASS, "B": TaskState.ASSIGNED, "C": TaskState.ASSIGNED}
    ready = Scheduler().ready_tasks(plan, states)
    assert [t.task_id for t in ready] == ["B", "C"]


def test_scheduler_waits_for_dependencies():
    plan = ProjectPlan([task("A"), task("B", ["A"])])
    states = {"A": TaskState.TEST, "B": TaskState.ASSIGNED}
    assert [t.task_id for t in Scheduler().ready_tasks(plan, states)] == ["A"]


def test_write_locks_detect_parent_child_conflict():
    locks = WriteLockManager()
    assert locks.acquire("A", ["src/backend"])
    assert not locks.acquire("B", ["src/backend/api"])
    assert locks.acquire("C", ["frontend"])
    locks.release("A")
    assert locks.acquire("B", ["src/backend/api"])
