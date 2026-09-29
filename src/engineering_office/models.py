from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ProjectState(str, Enum):
    NEW_PROJECT = "NEW_PROJECT"
    DISCOVERING = "DISCOVERING"
    PROJECT_MAPPED = "PROJECT_MAPPED"
    STAFFING = "STAFFING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    REVIEWING = "REVIEWING"
    VERIFYING = "VERIFYING"
    AUDIT_COMPLETE = "AUDIT_COMPLETE"
    AUDIT_COMPLETE_LIMITED = "AUDIT_COMPLETE_LIMITED"
    BLOCKED = "BLOCKED"
    PARTIAL = "PARTIAL"
    PASS = "PASS"
    FAIL = "FAIL"
    DELIVERED = "DELIVERED"


class TaskState(str, Enum):
    NEW = "NEW"
    TRIAGED = "TRIAGED"
    ASSIGNED = "ASSIGNED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    HYPOTHESIS = "HYPOTHESIS"
    EXPERIMENT = "EXPERIMENT"
    IMPLEMENTATION = "IMPLEMENTATION"
    REVIEW = "REVIEW"
    TEST = "TEST"
    VERIFY = "VERIFY"
    PASS = "PASS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    NEEDS_SPECIALIST = "NEEDS_SPECIALIST"
    REGRESSION_FAILED = "REGRESSION_FAILED"
    ESCALATED = "ESCALATED"


class Complexity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    ESCALATION = "ESCALATION"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class FeedbackDecision(str, Enum):
    APPROVE_FOR_IMPLEMENTATION = "APPROVE_FOR_IMPLEMENTATION"
    REJECT_HYPOTHESIS = "REJECT_HYPOTHESIS"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"


@dataclass(slots=True)
class ProjectMap:
    project_id: str
    root: str
    objective: str
    project_type: str
    technologies: list[str]
    working_components: list[str]
    broken_components: list[str]
    constraints: list[str]
    risk_areas: list[str]
    required_domains: list[str]
    unknowns: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentSpec:
    name: str
    mission: str
    capabilities: list[str]
    allowed_tools: list[str]
    read_scopes: list[str]
    write_scopes: list[str]
    forbidden_actions: list[str]
    model_tier: Complexity
    output_contract: list[str] = field(default_factory=lambda: [
        "observations", "hypotheses", "actions", "tests", "risks", "handoff"
    ])
    temporary: bool = True
    level: int = 3
    reports_to: str = "Office Director"
    lifecycle_state: str = "ACTIVE"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.mission.strip():
            raise ValueError("agent name and mission must be non-empty")
        if not self.capabilities:
            raise ValueError("agent must have at least one capability")


@dataclass(slots=True)
class TaskContract:
    task_id: str
    project_id: str
    goal: str
    owner: str
    dependencies: list[str]
    read_scopes: list[str]
    write_scopes: list[str]
    required_evidence: list[str]
    acceptance_criteria: list[str]
    prohibited_actions: list[str]
    complexity: Complexity
    risk: RiskLevel
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Hypothesis:
    hypothesis_id: str
    claim: str
    observations: list[str]
    evidence_for: list[str]
    evidence_against: list[str]
    alternatives: list[str]
    confidence: float
    discriminating_test: str
    expected_if_true: str
    expected_if_false: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(slots=True)
class ToolAction:
    tool: str
    args: dict[str, Any]
    reason: str


@dataclass(slots=True)
class AgentReport:
    status: str
    observations: list[str]
    interpretations: list[str]
    hypotheses: list[Hypothesis]
    actions: list[ToolAction]
    tests: list[str]
    risks: list[str]
    specialist_requests: list[dict[str, Any]] = field(default_factory=list)
    research_requests: list[dict[str, Any]] = field(default_factory=list)
    handoff: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerificationReport:
    verdict: Verdict
    checks: list[dict[str, Any]]
    evidence_refs: list[str]
    reasons: list[str]


_TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.NEW: {TaskState.TRIAGED, TaskState.BLOCKED},
    TaskState.TRIAGED: {TaskState.ASSIGNED, TaskState.NEEDS_RESEARCH, TaskState.NEEDS_SPECIALIST, TaskState.BLOCKED},
    TaskState.ASSIGNED: {TaskState.EVIDENCE_REQUIRED, TaskState.HYPOTHESIS, TaskState.IMPLEMENTATION, TaskState.BLOCKED},
    TaskState.EVIDENCE_REQUIRED: {TaskState.HYPOTHESIS, TaskState.NEEDS_RESEARCH, TaskState.BLOCKED},
    TaskState.HYPOTHESIS: {TaskState.EXPERIMENT, TaskState.REVIEW, TaskState.BLOCKED, TaskState.ESCALATED},
    TaskState.EXPERIMENT: {TaskState.HYPOTHESIS, TaskState.IMPLEMENTATION, TaskState.BLOCKED},
    TaskState.IMPLEMENTATION: {TaskState.REVIEW, TaskState.TEST, TaskState.BLOCKED},
    TaskState.REVIEW: {TaskState.IMPLEMENTATION, TaskState.TEST, TaskState.EVIDENCE_REQUIRED, TaskState.FAILED},
    TaskState.TEST: {TaskState.VERIFY, TaskState.IMPLEMENTATION, TaskState.REGRESSION_FAILED, TaskState.FAILED},
    TaskState.VERIFY: {TaskState.PASS, TaskState.FAILED, TaskState.BLOCKED, TaskState.IMPLEMENTATION},
    TaskState.REGRESSION_FAILED: {TaskState.IMPLEMENTATION, TaskState.FAILED},
    TaskState.NEEDS_RESEARCH: {TaskState.ASSIGNED, TaskState.BLOCKED},
    TaskState.NEEDS_SPECIALIST: {TaskState.ASSIGNED, TaskState.BLOCKED},
    TaskState.ESCALATED: {TaskState.ASSIGNED, TaskState.BLOCKED},
    TaskState.PASS: set(),
    TaskState.FAILED: {TaskState.ASSIGNED, TaskState.BLOCKED},
    TaskState.BLOCKED: {TaskState.ASSIGNED, TaskState.FAILED},
}


def legal_task_transition(source: TaskState, target: TaskState) -> bool:
    return target in _TASK_TRANSITIONS.get(source, set())


def dataclass_to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: dataclass_to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [dataclass_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: dataclass_to_jsonable(v) for k, v in value.items()}
    return value
