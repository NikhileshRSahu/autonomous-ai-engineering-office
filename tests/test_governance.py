from pathlib import Path
import json

from engineering_office.approvals import ApprovalManager
from engineering_office.communications import CommunicationManager, MessageKind
from engineering_office.control import OfficeControl
from engineering_office.decisions import DecisionLog
from engineering_office.models import AgentSpec, Complexity
from engineering_office.storage import OfficeStore
from engineering_office.workforce import WorkforceDecision, WorkforceManager, effective_complexity


def test_approval_manager_persists_and_builds_policy(tmp_path: Path):
    mgr=ApprovalManager(tmp_path/"approvals.json")
    req=mgr.request("rm -rf scratch","destructive","agent wants to remove generated scratch")
    assert mgr.policy().allows(req.action,req.risk_class) is False
    mgr.approve(req.approval_id)
    mgr2=ApprovalManager(tmp_path/"approvals.json")
    assert mgr2.policy().allows(req.action,req.risk_class) is True
    assert mgr2.list(status="APPROVED")[0].approval_id == req.approval_id


def test_control_pause_stop_resume_is_persistent(tmp_path: Path):
    c=OfficeControl(tmp_path/"control.json")
    c.pause(); assert OfficeControl(tmp_path/"control.json").state()["paused"] is True
    c.stop(); assert c.state()["stopped"] is True
    c.resume(); assert c.state() == {"paused":False,"stopped":False}


def test_communication_manager_forces_director_intervention_after_chatter(tmp_path: Path):
    store=OfficeStore(tmp_path/"db.sqlite")
    comms=CommunicationManager(store,max_non_actionable=2)
    comms.send("P","T","A","B",MessageKind.QUESTION,{"text":"why?"})
    comms.send("P","T","B","A",MessageKind.COMMENT,{"text":"thinking"})
    result=comms.send("P","T","A","B",MessageKind.QUESTION,{"text":"still?"})
    assert result["director_intervention"] is True
    assert any(m["kind"] == MessageKind.DIRECTOR_INTERVENTION.value for m in store.list_messages("P","T"))


def test_action_message_resets_chatter_counter(tmp_path: Path):
    store=OfficeStore(tmp_path/"db.sqlite")
    comms=CommunicationManager(store,max_non_actionable=2)
    comms.send("P","T","A","B",MessageKind.QUESTION,{})
    comms.send("P","T","A","B",MessageKind.ACTION,{"do":"test"})
    result=comms.send("P","T","A","B",MessageKind.QUESTION,{})
    assert result["director_intervention"] is False


def test_decision_log_records_structured_decision(tmp_path: Path):
    log=DecisionLog(tmp_path/"decisions")
    rec=log.record("database?",["sqlite","postgres"],"postgres","needs concurrency",["benchmark-1"],["ops complexity"])
    loaded=log.get(rec.decision_id)
    assert loaded.selected == "postgres"
    assert loaded.evidence == ["benchmark-1"]


def test_workforce_manager_recommends_replace_for_false_passes():
    mgr=WorkforceManager()
    assert mgr.assess({"tasks":5,"verified_success_rate":0.8,"false_pass_rate":0.2}) is WorkforceDecision.REPLACE
    assert mgr.assess({"tasks":5,"verified_success_rate":0.3,"false_pass_rate":0.0}) is WorkforceDecision.COACH
    assert mgr.assess({"tasks":5,"verified_success_rate":0.9,"false_pass_rate":0.0}) is WorkforceDecision.RETAIN


def test_effective_complexity_escalates_unreliable_agent():
    assert effective_complexity(Complexity.MEDIUM,{"tasks":4,"verified_success_rate":0.25,"false_pass_rate":0.0}) is Complexity.HIGH
    assert effective_complexity(Complexity.HIGH,{"tasks":2,"verified_success_rate":0.0,"false_pass_rate":0.5}) is Complexity.ESCALATION
