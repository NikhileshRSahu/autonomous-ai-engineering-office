from engineering_office.feedback import AdversarialCritic, EvidenceAnalyst, FeedbackLoop
from engineering_office.models import AgentReport, FeedbackDecision, ToolAction


def report(obs=None, actions=None, action_results=None, hypotheses=None):
    raw={}
    if action_results is not None: raw["action_results"]=action_results
    return AgentReport(
        status="COMPLETE", observations=obs or [], interpretations=[], hypotheses=hypotheses or [],
        actions=actions or [], tests=["pytest"], risks=[], raw=raw,
    )


def test_feedback_requires_evidence_for_substantive_change():
    r=report(obs=[], actions=[ToolAction("filesystem.write", {"path":"src/x.py","content":"x"}, "fix")])
    decision=FeedbackLoop(max_cycles=3).evaluate(r, evidence_refs=[])
    assert decision.decision is FeedbackDecision.MORE_EVIDENCE_REQUIRED


def test_feedback_rejects_failed_tool_action():
    r=report(obs=["failure reproduced"], actions=[ToolAction("shell", {"command":"pytest"}, "test")], action_results=[{"ok":False,"returncode":1}])
    decision=FeedbackLoop(max_cycles=3).evaluate(r, evidence_refs=["e1"])
    assert decision.decision is FeedbackDecision.REJECT_HYPOTHESIS


def test_critic_rejects_symptom_masking_test_disable():
    r=report(obs=["test fails"], actions=[ToolAction("filesystem.write", {"path":"tests/test_x.py","content":"import pytest\npytest.skip('ignore', allow_module_level=True)"}, "make pass")])
    d=AdversarialCritic().review(r)
    assert d.decision is FeedbackDecision.REJECT_HYPOTHESIS
    assert "mask" in " ".join(d.reasons).lower() or "disable" in " ".join(d.reasons).lower()


def test_feedback_approves_evidence_backed_successful_action():
    r=report(obs=["reproduced failing test"], actions=[ToolAction("filesystem.write", {"path":"src/x.py","content":"fixed"}, "fix")], action_results=[{"ok":True,"returncode":0}])
    d=FeedbackLoop(max_cycles=3).evaluate(r, evidence_refs=["failure-log","diff"])
    assert d.decision is FeedbackDecision.APPROVE_FOR_IMPLEMENTATION


def test_loop_is_bounded():
    loop=FeedbackLoop(max_cycles=2)
    r=report(obs=[], actions=[ToolAction("filesystem.write", {"path":"src/x.py","content":"x"}, "fix")])
    first=loop.evaluate(r, evidence_refs=[])
    second=loop.evaluate(r, evidence_refs=[])
    third=loop.evaluate(r, evidence_refs=[])
    assert first.decision is FeedbackDecision.MORE_EVIDENCE_REQUIRED
    assert second.decision is FeedbackDecision.MORE_EVIDENCE_REQUIRED
    assert third.blocked is True
