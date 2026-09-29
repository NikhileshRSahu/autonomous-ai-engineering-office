from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from .models import AgentReport, FeedbackDecision


@dataclass(slots=True)
class FeedbackRecord:
    decision: FeedbackDecision
    reasons: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    blocked: bool = False


class EvidenceAnalyst:
    def analyze(self, report: AgentReport, evidence_refs: list[str]) -> FeedbackRecord:
        if report.actions and not report.observations:
            return FeedbackRecord(
                FeedbackDecision.MORE_EVIDENCE_REQUIRED,
                ["substantive actions were proposed without recorded observations"],
                ["observation/evidence supporting the proposed change"],
            )
        if report.actions and not evidence_refs:
            return FeedbackRecord(
                FeedbackDecision.MORE_EVIDENCE_REQUIRED,
                ["substantive actions have no persisted evidence references"],
                ["persisted reproduction/test evidence"],
            )
        return FeedbackRecord(FeedbackDecision.APPROVE_FOR_IMPLEMENTATION, ["minimum evidence contract satisfied"])


class DomainReviewer:
    def review(self, report: AgentReport) -> FeedbackRecord:
        results = report.raw.get("action_results", [])
        failed = [r for r in results if not r.get("ok", False)]
        if failed:
            return FeedbackRecord(
                FeedbackDecision.REJECT_HYPOTHESIS,
                [f"{len(failed)} tool/action result(s) failed; implementation evidence is not valid"],
            )
        return FeedbackRecord(FeedbackDecision.APPROVE_FOR_IMPLEMENTATION, ["executed actions report success"])


class AdversarialCritic:
    _MASKING_MARKERS = [
        "pytest.skip", "@pytest.mark.skip", "@unittest.skip", "test.skip(",
        "describe.skip(", "xit(", "xdescribe(", "assert true", "|| true", "exit 0",
    ]

    def review(self, report: AgentReport) -> FeedbackRecord:
        reasons=[]
        for action in report.actions:
            path = str(action.args.get("path", "")).replace("\\", "/").lower()
            content = str(action.args.get("content", "")).lower()
            new = str(action.args.get("new", "")).lower()
            combined = content + "\n" + new
            if path.startswith("acceptance/") or "/acceptance/" in path:
                reasons.append("candidate attempted to modify acceptance gates")
            if ("test" in path or "spec" in path) and any(marker in combined for marker in self._MASKING_MARKERS):
                reasons.append("candidate appears to disable or mask a failing test")
            if action.tool == "shell":
                command = str(action.args.get("command", "")).lower()
                if any(x in command for x in ["pytest -x --maxfail=0", "|| true", "exit 0"]):
                    reasons.append("candidate test command may mask failure")
        if reasons:
            return FeedbackRecord(FeedbackDecision.REJECT_HYPOTHESIS, reasons)
        return FeedbackRecord(FeedbackDecision.APPROVE_FOR_IMPLEMENTATION, ["no benchmark/test masking pattern detected"])


class FeedbackLoop:
    def __init__(self, max_cycles: int = 4):
        if max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")
        self.max_cycles = max_cycles
        self.cycles = 0
        self.evidence_analyst = EvidenceAnalyst()
        self.domain_reviewer = DomainReviewer()
        self.critic = AdversarialCritic()

    def evaluate(self, report: AgentReport, evidence_refs: list[str]) -> FeedbackRecord:
        self.cycles += 1
        if self.cycles > self.max_cycles:
            return FeedbackRecord(
                FeedbackDecision.MORE_EVIDENCE_REQUIRED,
                ["feedback cycle limit reached; Director intervention required"],
                blocked=True,
            )
        stages = [
            self.evidence_analyst.analyze(report, evidence_refs),
            self.domain_reviewer.review(report),
            self.critic.review(report),
        ]
        for record in stages:
            if record.decision is FeedbackDecision.REJECT_HYPOTHESIS:
                return record
        missing=[]; reasons=[]
        for record in stages:
            if record.decision is FeedbackDecision.MORE_EVIDENCE_REQUIRED:
                missing.extend(record.missing_evidence); reasons.extend(record.reasons)
        if missing:
            return FeedbackRecord(FeedbackDecision.MORE_EVIDENCE_REQUIRED, reasons, missing)
        return FeedbackRecord(
            FeedbackDecision.APPROVE_FOR_IMPLEMENTATION,
            [reason for record in stages for reason in record.reasons],
        )
