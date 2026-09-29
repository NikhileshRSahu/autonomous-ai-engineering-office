from __future__ import annotations
from dataclasses import dataclass
from .models import TaskContract


@dataclass(slots=True)
class ProjectPlan:
    tasks: list[TaskContract]

    def by_id(self) -> dict[str, TaskContract]:
        return {t.task_id: t for t in self.tasks}


class PlanValidator:
    @staticmethod
    def validate(plan: ProjectPlan) -> None:
        by_id = plan.by_id()
        if len(by_id) != len(plan.tasks):
            raise ValueError("duplicate task id")
        for task in plan.tasks:
            unknown = [d for d in task.dependencies if d not in by_id]
            if unknown:
                raise ValueError(f"unknown dependencies for {task.task_id}: {unknown}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(node: str) -> None:
            if node in visiting:
                raise ValueError("dependency cycle detected")
            if node in visited:
                return
            visiting.add(node)
            for dep in by_id[node].dependencies:
                dfs(dep)
            visiting.remove(node)
            visited.add(node)

        for node in by_id:
            dfs(node)


def task_model_family(task: TaskContract) -> str:
    explicit = str(task.metadata.get("model_family", "")).strip().lower()
    if explicit in {"qwen", "nemotron", "none"}:
        return explicit
    return "nemotron" if task.complexity.value in {"HIGH", "ESCALATION"} else "qwen"
