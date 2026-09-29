from __future__ import annotations
import json
from .models import AgentSpec, TaskContract, dataclass_to_jsonable

SYSTEM_RULES = """You are a specialist inside an engineering office.
Evidence outranks confidence. Separate observations from interpretations.
Never weaken acceptance gates, hide failures, disable safety checks, or claim PASS.
Stay within assigned authority and tool/write scopes. Prefer a discriminating test before broad edits.
Return ONLY a JSON object matching the requested schema."""


def build_agent_messages(agent: AgentSpec, task: TaskContract, context: dict) -> list[dict[str, str]]:
    schema = {
        "status":"CONTINUE|COMPLETE|BLOCKED|FAILED|NEEDS_RESEARCH|NEEDS_SPECIALIST",
        "observations":["fact"],
        "interpretations":["inference"],
        "hypotheses":[{
            "hypothesis_id":"H1","claim":"...","observations":[],"evidence_for":[],"evidence_against":[],
            "alternatives":[],"confidence":0.5,"discriminating_test":"...","expected_if_true":"...","expected_if_false":"..."
        }],
        "actions":[{"tool":"tool.name","args":{},"reason":"..."}],
        "tests":[],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":""
    }
    payload = {
        "agent": dataclass_to_jsonable(agent),
        "task": dataclass_to_jsonable(task),
        "context": context,
        "required_output_schema": schema,
    }
    return [
        {"role":"system","content":SYSTEM_RULES},
        {"role":"user","content":json.dumps(payload, sort_keys=True, default=str)},
    ]
