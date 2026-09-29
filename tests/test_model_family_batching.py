from engineering_office.models import Complexity, RiskLevel, TaskContract, TaskState
from engineering_office.planning import ProjectPlan
from engineering_office.scheduler import Scheduler


def task(tid, family, deps=None, scope=None):
    return TaskContract(tid,"P",tid,tid, deps or [], ["."], [scope or tid], [], [], [], Complexity.HIGH if family=="nemotron" else Complexity.LOW, RiskLevel.LOW, {"model_family":family})


def test_qwen_grouping_keeps_deterministic_tasks_eligible():
    plan=ProjectPlan([task("q1","qwen"),task("n1","nemotron"),task("d1","none"),task("q2","qwen")])
    states={t.task_id:TaskState.ASSIGNED for t in plan.tasks}
    batch=Scheduler().next_batch(plan,states,preferred_model_family="qwen",limit=3)
    assert [t.task_id for t in batch] == ["q1","q2","d1"]


def test_dependency_barrier_beats_affinity():
    plan=ProjectPlan([task("n1","nemotron"),task("q1","qwen",["n1"])])
    states={"n1":TaskState.ASSIGNED,"q1":TaskState.ASSIGNED}
    batch=Scheduler().next_batch(plan,states,preferred_model_family="qwen",limit=2)
    assert [t.task_id for t in batch] == ["n1"]


def test_lock_conflicts_and_approval_blocks_are_excluded():
    plan=ProjectPlan([task("q1","qwen",scope="src"),task("q2","qwen",scope="src/sub"),task("q3","qwen",scope="docs")])
    states={t.task_id:TaskState.ASSIGNED for t in plan.tasks}
    batch=Scheduler().next_batch(plan,states,preferred_model_family="qwen",limit=3,locked_scopes=["src"],blocked_task_ids={"q3"})
    assert batch == []


def test_anti_starvation_falls_back_when_preferred_family_absent():
    plan=ProjectPlan([task("n1","nemotron"),task("n2","nemotron")])
    states={t.task_id:TaskState.ASSIGNED for t in plan.tasks}
    batch=Scheduler().next_batch(plan,states,preferred_model_family="qwen",limit=1)
    assert [t.task_id for t in batch] == ["n1"]
