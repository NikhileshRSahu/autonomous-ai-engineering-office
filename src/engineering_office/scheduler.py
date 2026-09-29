from __future__ import annotations
from pathlib import PurePosixPath
from .models import TaskState
from .planning import ProjectPlan, task_model_family


_TERMINAL = {TaskState.PASS, TaskState.FAILED, TaskState.BLOCKED}


class Scheduler:
    def ready_tasks(self, plan: ProjectPlan, states: dict[str, TaskState]):
        by_id = plan.by_id()
        ready = []
        for task in plan.tasks:
            state = states.get(task.task_id, TaskState.NEW)
            if state in _TERMINAL:
                continue
            if all(states.get(dep) is TaskState.PASS for dep in task.dependencies):
                ready.append(task)
        return ready

    def next_batch(
        self,
        plan: ProjectPlan,
        states: dict[str, TaskState],
        *,
        preferred_model_family: str | None = None,
        limit: int | None = None,
        locked_scopes: list[str] | None = None,
        blocked_task_ids: set[str] | None = None,
    ):
        ready = self.ready_tasks(plan, states)
        blocked_task_ids = blocked_task_ids or set()
        locked_scopes = locked_scopes or []
        ready = [t for t in ready if t.task_id not in blocked_task_ids and not any(WriteLockManager._conflict(scope, locked) for scope in t.write_scopes for locked in locked_scopes)]
        if not ready:
            return []
        family = (preferred_model_family or "").lower()
        if family:
            preferred = [t for t in ready if task_model_family(t) == family]
            deterministic = [t for t in ready if task_model_family(t) == "none"]
            others = [t for t in ready if t not in preferred and t not in deterministic]
            ordered = preferred + deterministic + others if preferred else ready
        else:
            ordered = ready
        return ordered[:limit] if limit is not None else ordered


class WriteLockManager:
    def __init__(self):
        self._locks: dict[str, list[str]] = {}

    @staticmethod
    def _norm(scope: str) -> str:
        s = str(PurePosixPath(scope.strip() or "."))
        return "." if s == "." else s.strip("/")

    @classmethod
    def _conflict(cls, a: str, b: str) -> bool:
        a, b = cls._norm(a), cls._norm(b)
        if "." in {a, b}:
            return True
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")

    def acquire(self, owner: str, scopes: list[str]) -> bool:
        for other, locked in self._locks.items():
            if other == owner:
                continue
            if any(self._conflict(a, b) for a in scopes for b in locked):
                return False
        self._locks[owner] = list(scopes)
        return True

    def release(self, owner: str) -> None:
        self._locks.pop(owner, None)

    def snapshot(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._locks.items()}
