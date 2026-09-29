from __future__ import annotations
import json
from typing import Any

from .models import AgentSpec, Complexity, ProjectMap, RiskLevel, TaskContract, dataclass_to_jsonable
from .models_runtime import ModelProvider
from .planning import PlanValidator, ProjectPlan


class PlanGenerationError(RuntimeError):
    pass


class ModelPlanGenerator:
    def __init__(self, provider: ModelProvider):
        self.provider=provider

    def generate(self, project: ProjectMap, agents: list[AgentSpec]) -> ProjectPlan:
        allowed={a.name:a for a in agents}
        prompt={
            "project":dataclass_to_jsonable(project),
            "available_agents":[dataclass_to_jsonable(a) for a in agents],
            "rules":[
                "Use only listed agent names as owners.",
                "Use only write scopes already granted to that owner.",
                "Create small dependency-aware tasks; independent tasks may run in parallel.",
                "Each task must include one or more objective command gates whenever executable verification exists.",
                "Never make acceptance weaker than the project objective.",
            ],
            "schema":{"tasks":[{
                "task_id":"T-001","goal":"...","owner":"exact listed name","dependencies":[],
                "write_scopes":[],"required_evidence":[],"acceptance_criteria":[],"prohibited_actions":[],
                "complexity":"LOW|MEDIUM|HIGH|ESCALATION","risk":"LOW|MEDIUM|HIGH|CRITICAL",
                "gates":[{"name":"...","command":"...","expected_exit":0,"required_output":None,"timeout":300}],
                "verification_required_evidence":[]
            }]}
        }
        response=self.provider.complete([
            {"role":"system","content":"You are the Project Manager. Return ONLY valid JSON. Build an evidence-driven engineering DAG without inventing permissions."},
            {"role":"user","content":json.dumps(prompt,sort_keys=True,default=str)},
        ],response_format={"type":"json_object"})
        try:
            raw=json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise PlanGenerationError(f"planner returned invalid JSON: {exc}") from exc
        if not isinstance(raw,dict) or not isinstance(raw.get("tasks"),list) or not raw["tasks"]:
            raise PlanGenerationError("planner must return a non-empty tasks list")
        tasks=[]
        for item in raw["tasks"]:
            if not isinstance(item,dict): raise PlanGenerationError("each task must be an object")
            owner=str(item.get("owner",""))
            if owner not in allowed: raise PlanGenerationError(f"task owner is not an available agent: {owner}")
            agent=allowed[owner]
            writes=[str(x) for x in item.get("write_scopes",[])]
            if any(scope not in agent.write_scopes for scope in writes):
                raise PlanGenerationError(f"task write scope exceeds owner authority: {writes} vs {agent.write_scopes}")
            gates=item.get("gates",[])
            if gates is not None and not isinstance(gates,list): raise PlanGenerationError("gates must be a list")
            try:
                task=TaskContract(
                    task_id=str(item["task_id"]), project_id=project.project_id, goal=str(item["goal"]), owner=owner,
                    dependencies=[str(x) for x in item.get("dependencies",[])], read_scopes=list(agent.read_scopes),
                    write_scopes=writes, required_evidence=[str(x) for x in item.get("required_evidence",[])],
                    acceptance_criteria=[str(x) for x in item.get("acceptance_criteria",[])],
                    prohibited_actions=list(dict.fromkeys(agent.forbidden_actions + [str(x) for x in item.get("prohibited_actions",[])])),
                    complexity=Complexity(str(item.get("complexity","MEDIUM"))), risk=RiskLevel(str(item.get("risk","MEDIUM"))),
                    metadata={
                        "gates":gates or [],
                        "verification_required_evidence":[str(x) for x in item.get("verification_required_evidence",[])],
                        "model_generated_plan":True,
                    },
                )
            except (KeyError,ValueError,TypeError) as exc:
                raise PlanGenerationError(f"invalid task contract: {exc}") from exc
            tasks.append(task)
        plan=ProjectPlan(tasks)
        PlanValidator.validate(plan)
        return plan
