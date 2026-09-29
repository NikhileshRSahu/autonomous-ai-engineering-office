from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

from .agent_factory import AgentFactory
from .agent_control import AgentControlManager
from .approvals import ApprovalManager
from .communications import CommunicationManager, MessageKind
from .control import OfficeControl
from .decisions import DecisionLog
from .agent_runtime import AgentProtocolError, AgentRuntime
from .capabilities import CapabilityRegistry
from .delivery import DeliveryManager
from .discovery import ProjectDiscovery
from .evidence import EvidenceStore
from .feedback import FeedbackLoop
from .fast_audit import AuditModePolicy
from .memory import MemoryManager
from .models import (
    AgentSpec, Complexity, ProjectMap, ProjectState, RiskLevel, TaskContract, TaskState,
    Verdict, dataclass_to_jsonable,
)
from .models_runtime import ModelRouter, ModelProvider
from .model_planning import ModelPlanGenerator
from .research import ResearchManager, ResearchRequest
from .runtime_events import RuntimeEventStore, emit_runtime_event
from .run_records import RunCoordinator
from .planning import PlanValidator, ProjectPlan
from .scheduler import Scheduler, WriteLockManager
from .security import ApprovalPolicy, PermissionSet, SecurityError, classify_command
from .storage import OfficeStore
from .tools import FileReadTool, FileSearchTool, FileWriteTool, GitTool, ReplaceTextTool, ShellTool, ToolRegistry
from .verification import AcceptanceSnapshot, AcceptanceSpec, Verifier
from .workforce import WorkforceManager, effective_complexity


class OfficeEngine:
    def __init__(self, project_root: str | Path, model_router: ModelRouter | None = None, max_task_iterations: int = 6, parallelism: int = 1, research_manager: ResearchManager | None = None, max_feedback_cycles: int = 4):
        self.root = Path(project_root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"project root is not a directory: {self.root}")
        self.office_dir = self.root / ".office"
        self.office_dir.mkdir(parents=True, exist_ok=True)
        self.store = OfficeStore(self.office_dir / "state.db")
        self.runtime_events = RuntimeEventStore(self.root)
        self.run_coordinator: RunCoordinator | None = None
        self.evidence = EvidenceStore(self.office_dir / "evidence")
        self.memory = MemoryManager(self.store)
        self.discovery = ProjectDiscovery()
        self.factory = AgentFactory(CapabilityRegistry.default())
        self.model_router = model_router
        self.max_task_iterations = max(1, max_task_iterations)
        self.max_feedback_cycles = max(1, max_feedback_cycles)
        self.parallelism = max(1, parallelism)
        self.research_manager = research_manager or ResearchManager(None)
        self.approvals = ApprovalManager(self.office_dir / "approvals.json")
        self.control = OfficeControl(self.office_dir / "control.json")
        self.agent_control = AgentControlManager(self.office_dir / "agent_controls.json")
        self.comms = CommunicationManager(self.store, event_sink=self._record_message_event)
        self.decisions = DecisionLog(self.office_dir / "decisions")
        self.workforce = WorkforceManager()
        lifecycle = getattr(self.model_router, "lifecycle_manager", None) if self.model_router is not None else None
        if lifecycle is not None:
            previous_sink = getattr(lifecycle, "_event_sink", None)
            def chained_model_sink(data):
                if previous_sink is not None:
                    previous_sink(data)
                self._record_model_event(data)
            lifecycle._event_sink = chained_model_sink
        for d in ["agents", "acceptance", "research", "runs", "delivery", "knowledge", "tickets", "experiments", "failures", "fixes", "regressions", "messages"]:
            (self.office_dir / d).mkdir(parents=True, exist_ok=True)

    def _runtime_project_id(self) -> str:
        try:
            return self._load_project().project_id
        except Exception:
            return "UNINITIALIZED"

    def _emit_runtime(self, kind: str, summary: str, *, project_id: str | None = None, agent_id: str | None = None, task_id: str | None = None, payload: dict[str, Any] | None = None, severity: str = "info", source: str = "office", correlation_id: str | None = None):
        return emit_runtime_event(self.runtime_events, project_id=project_id or self._runtime_project_id(), agent_id=agent_id, task_id=task_id, kind=kind, summary=summary, payload=payload or {}, severity=severity, source=source, correlation_id=correlation_id)

    def _record_message_event(self, project_id: str, task_id: str | None, sender: str, recipient: str, kind: str, data: dict[str, Any]) -> None:
        self._emit_runtime("message.sent", f"{sender} → {recipient}: {kind}", project_id=project_id, agent_id=sender, task_id=task_id, payload={"sender": sender, "recipient": recipient, "message_kind": kind, "data": data}, source="message")

    def _record_model_event(self, data: dict[str, Any]) -> None:
        kind = str(data.get("event", "model.event"))
        model = str(data.get("model", "local-model"))
        payload = {k: v for k, v in data.items() if k not in {"event", "timestamp"}}
        self._emit_runtime(kind, f"{model}: {kind.split('.')[-1]}", payload=payload, source="model")

    def start(self, objective: str) -> dict[str, Any]:
        project = self.discovery.inspect(self.root, objective)
        self.store.upsert_project(project, ProjectState.DISCOVERING)
        self.store.add_event(project.project_id, None, "project.discovered", dataclass_to_jsonable(project))
        self._emit_runtime("project.discovered", f"Discovered {Path(project.root).name or project.project_type}", project_id=project.project_id, payload={"root": project.root, "project_type": project.project_type, "technologies": project.technologies})
        self.store.set_project_state(project.project_id, ProjectState.PROJECT_MAPPED)
        self._write_json(self.office_dir / "project.json", dataclass_to_jsonable(project))

        self.store.set_project_state(project.project_id, ProjectState.STAFFING)
        agents = self.factory.staff(project)
        self._save_agents(agents)
        self.store.add_event(project.project_id, None, "project.staffed", {"agents": [a.name for a in agents]})
        self._emit_runtime("project.staffed", f"Staffed {len(agents)} specialists", project_id=project.project_id, payload={"agents": [a.name for a in agents]})

        self._prepare_acceptance(project)
        self.store.set_project_state(project.project_id, ProjectState.PLANNING)
        plan = self._fallback_plan(project, agents)
        PlanValidator.validate(plan)
        self._save_plan(plan)
        for task in plan.tasks:
            self.store.upsert_task(task, TaskState.ASSIGNED)
        self.store.add_event(project.project_id, None, "project.planned", {"tasks": [t.task_id for t in plan.tasks]})
        self._emit_runtime("project.planned", f"Planned {len(plan.tasks)} tasks", project_id=project.project_id, payload={"tasks": [t.task_id for t in plan.tasks]})
        return {
            "project": dataclass_to_jsonable(project),
            "agents": [dataclass_to_jsonable(a) for a in agents],
            "tasks": [dataclass_to_jsonable(t) for t in plan.tasks],
            "acceptance": str(self._acceptance_path()),
        }

    def pause(self) -> None:
        self.control.pause()
        try:
            project=self._load_project(); self.store.add_event(project.project_id,None,"office.paused",{})
        except RuntimeError:
            pass

    def stop(self) -> None:
        self.control.stop()
        try:
            project=self._load_project(); self.store.add_event(project.project_id,None,"office.stopped",{})
        except RuntimeError:
            pass

    def resume(self, reset_blocked: bool = False) -> None:
        self.control.resume()
        try:
            project=self._load_project()
        except RuntimeError:
            return
        if reset_blocked:
            for task,state in self.store.list_tasks(project.project_id):
                if state is TaskState.BLOCKED:
                    self.store.set_task_state(task.task_id,TaskState.ASSIGNED)
        self.store.add_event(project.project_id,None,"office.resumed",{"reset_blocked":reset_blocked})

    def pause_agent(self, agent_name: str) -> dict[str, Any]:
        self._require_agent(agent_name)
        state = self.agent_control.pause(agent_name)
        project = self._load_project()
        self.store.add_event(project.project_id, None, "agent.paused", {"agent": agent_name})
        return {"agent": agent_name, **state}

    def halt_agent(self, agent_name: str) -> dict[str, Any]:
        self._require_agent(agent_name)
        state = self.agent_control.halt(agent_name)
        project = self._load_project()
        self.store.add_event(project.project_id, None, "agent.halted", {"agent": agent_name})
        return {"agent": agent_name, **state}

    def resume_agent(self, agent_name: str, reset_blocked: bool = True) -> dict[str, Any]:
        self._require_agent(agent_name)
        state = self.agent_control.resume(agent_name)
        project = self._load_project()
        if reset_blocked:
            for task, task_state in self.store.list_tasks(project.project_id):
                if task.owner == agent_name and task_state is TaskState.BLOCKED:
                    self.store.set_task_state(task.task_id, TaskState.ASSIGNED)
        self.store.add_event(project.project_id, None, "agent.resumed", {"agent": agent_name, "reset_blocked": reset_blocked})
        return {"agent": agent_name, **state}

    def steer_agent(self, agent_name: str, message: str) -> dict[str, Any]:
        self._require_agent(agent_name)
        if not message.strip():
            raise ValueError("steering message must be non-empty")
        project = self._load_project()
        task_id = next((task.task_id for task, state in self.store.list_tasks(project.project_id) if task.owner == agent_name and state not in {TaskState.PASS, TaskState.FAILED}), None)
        result = self.comms.send(project.project_id, task_id, "User", agent_name, MessageKind.STEER, {"message": message.strip()})
        self.store.add_event(project.project_id, task_id, "agent.steered", {"agent": agent_name, "message": message.strip(), "message_id": result["message_id"]})
        return {"recipient": agent_name, "task_id": task_id, "message": message.strip(), **result}

    def _require_agent(self, agent_name: str) -> AgentSpec:
        agent = next((item for item in self._load_agents() if item.name == agent_name), None)
        if agent is None:
            raise KeyError(agent_name)
        return agent

    def update_objective(self, objective: str) -> ProjectMap:
        if not objective.strip(): raise ValueError("objective must be non-empty")
        project=self._load_project(); project.objective=objective.strip()
        state=self.store.get_project_state(project.project_id)
        self.store.upsert_project(project,state); self._write_json(self.office_dir/"project.json",dataclass_to_jsonable(project))
        self.store.add_event(project.project_id,None,"project.objective_changed",{"objective":project.objective})
        return project

    def add_agent(self, expertise: str) -> AgentSpec:
        if not expertise.strip():
            raise ValueError("expertise must be non-empty")
        project = self._load_project()
        agents = self._load_agents()
        specialist = self.factory.create_specialist(expertise.strip(), "user added this specialist to the office", [], [])
        base_name = specialist.name
        existing = {agent.name for agent in agents}
        suffix = 2
        while specialist.name in existing:
            specialist.name = f"{base_name} {suffix}"
            suffix += 1
        agents.append(specialist)
        self._save_agents(agents)
        self.store.add_event(project.project_id, None, "agent.added", {"agent": specialist.name, "expertise": expertise.strip()})
        return specialist

    def replace_agent(self, old_name: str, expertise: str) -> AgentSpec:
        agents=self._load_agents(); old=next((a for a in agents if a.name==old_name),None)
        if old is None: raise KeyError(old_name)
        replacement=self.factory.create_specialist(expertise,f"user-requested replacement for {old_name}",list(old.write_scopes),list(old.allowed_tools))
        replacement.level=old.level; replacement.reports_to=old.reports_to
        old.lifecycle_state="ARCHIVED"
        agents=[replacement if a.name==old_name else a for a in agents]
        self._save_agents(agents)
        plan=self._load_plan()
        for task in plan.tasks:
            if task.owner==old_name:
                task.owner=replacement.name
                self.store.upsert_task(task,self.store.get_task_state(task.task_id))
        self._save_plan(plan)
        project=self._load_project(); self.store.add_event(project.project_id,None,"agent.replaced",{"old":old_name,"new":replacement.name,"expertise":expertise})
        return replacement

    def status(self) -> dict[str, Any]:
        project = self._load_project()
        tasks = self.store.list_tasks(project.project_id)
        run = None
        timing = None
        try:
            coordinator = self.run_coordinator or RunCoordinator(self.root, project_id=project.project_id, event_store=self.runtime_events)
            run = coordinator.active().to_dict()
            timing = coordinator.timing()
        except RuntimeError:
            pass
        return {
            "project_id": project.project_id,
            "project_state": self.store.get_project_state(project.project_id).value,
            "objective": project.objective,
            "technologies": project.technologies,
            "tasks": [{"task": dataclass_to_jsonable(t), "state": s.value} for t, s in tasks],
            "agents": [dataclass_to_jsonable(a) for a in self._load_agents()],
            "active_run": run,
            "run_timing": timing,
        }

    def plan_with_model(self, provider: ModelProvider) -> dict[str, Any]:
        project=self._load_project()
        agents=self._load_agents()
        plan=ModelPlanGenerator(provider).generate(project,agents)
        self.store.delete_tasks(project.project_id)
        self._save_plan(plan)
        task_accept_dir=self.office_dir / "acceptance" / "tasks"
        if task_accept_dir.exists():
            for old in task_accept_dir.glob("*.json"): old.unlink()
        task_accept_dir.mkdir(parents=True,exist_ok=True)
        for task in plan.tasks:
            self.store.upsert_task(task,TaskState.ASSIGNED)
            gates=task.metadata.get("gates") or []
            if gates:
                self._write_json(task_accept_dir / f"{task.task_id}.json", {
                    "gates":gates,
                    "required_evidence":task.metadata.get("verification_required_evidence",[]),
                })
        self.store.add_event(project.project_id,None,"project.replanned",{"tasks":[t.task_id for t in plan.tasks],"source":"model"})
        return {"tasks":[dataclass_to_jsonable(t) for t in plan.tasks]}

    def run_mode(self, mode: str = "complete", objective: str | None = None, *, max_context_files: int = 30, max_context_chars: int = 200_000, simulation_requested: bool = False) -> dict[str, Any]:
        mode = str(mode or "complete").lower().strip()
        if mode in {"fast-audit", "check-report"}:
            from .audit_runner import FastAuditRunner
            return FastAuditRunner(self, max_context_files=max_context_files, max_context_chars=max_context_chars).run(mode, objective, simulation_requested=simulation_requested)
        if mode not in {"complete", "fix", "custom"}:
            raise ValueError(f"unsupported run mode: {mode}")
        return self.run()

    def run(self) -> dict[str, Any]:
        project = self._load_project()
        control=self.control.state()
        if control.get("paused"):
            return {"project_id":project.project_id,"project_state":self.store.get_project_state(project.project_id).value,"control":"PAUSED","task_results":[]}
        if control.get("stopped"):
            return {"project_id":project.project_id,"project_state":self.store.get_project_state(project.project_id).value,"control":"STOPPED","task_results":[]}
        plan = self._load_plan()
        agents = {a.name: a for a in self._load_agents()}
        self.store.set_project_state(project.project_id, ProjectState.EXECUTING)
        task_results=[]
        scheduler=Scheduler()
        locks=WriteLockManager()

        while True:
            control=self.control.state()
            if control.get("paused") or control.get("stopped"):
                task_results.append({"state":"BLOCKED","reason":"office control requested pause/stop between task batches"})
                break
            rows=self.store.list_tasks(project.project_id)
            states={task.task_id:state for task,state in rows}
            nonterminal=[task for task,state in rows if state not in {TaskState.PASS,TaskState.FAILED,TaskState.BLOCKED}]
            if not nonterminal:
                break
            ready=scheduler.ready_tasks(plan,states)
            if not ready:
                for task in nonterminal:
                    self.store.set_task_state(task.task_id,TaskState.BLOCKED)
                    task_results.append({"task_id":task.task_id,"state":"BLOCKED","reason":"no runnable task; dependency chain is blocked"})
                break
            if self.model_router is not None:
                ready=self.model_router.order_tasks_for_residency(ready)
                candidates=self.model_router.same_model_batch(ready,self.parallelism)
            else:
                candidates=ready[:self.parallelism]
            batch=[]
            for task in candidates:
                if locks.acquire(task.task_id, task.write_scopes):
                    batch.append(task)
            if not batch:
                task=ready[0]; locks.acquire(task.task_id,task.write_scopes); batch=[task]

            def execute(task: TaskContract):
                agent=agents.get(task.owner)
                if agent is None:
                    self.store.set_task_state(task.task_id,TaskState.BLOCKED)
                    return {"task_id":task.task_id,"state":"BLOCKED","reason":"owner agent missing"}
                agent_state = self.agent_control.state(agent.name)["state"]
                if agent_state in {"paused", "halted"}:
                    self.store.set_task_state(task.task_id, TaskState.BLOCKED)
                    self.store.add_event(project.project_id, task.task_id, f"agent.{agent_state}_blocked", {"agent": agent.name})
                    return {"task_id": task.task_id, "state": "BLOCKED", "reason": f"owner agent is {agent_state}"}
                return self._execute_task(project,task,agent)

            if len(batch)==1:
                results=[execute(batch[0])]
            else:
                with ThreadPoolExecutor(max_workers=len(batch),thread_name_prefix="office-task") as pool:
                    futures={pool.submit(execute,t):t for t in batch}
                    results=[future.result() for future in as_completed(futures)]
            for task in batch:
                locks.release(task.task_id)
            task_results.extend(results)

        states = [state for _, state in self.store.list_tasks(project.project_id)]
        if states and all(s is TaskState.PASS for s in states):
            final_state = ProjectState.PASS
        elif any(s is TaskState.BLOCKED for s in states):
            final_state = ProjectState.BLOCKED
        else:
            final_state = ProjectState.FAIL
        self.store.set_project_state(project.project_id, final_state)
        self.store.add_event(project.project_id, None, "project.run_finished", {"state":final_state.value})
        return {
            "project_id": project.project_id,
            "project_state": final_state.value,
            "task_results": task_results,
            "evidence": [dataclass_to_jsonable(r) for r in self.evidence.list_refs(project.project_id)],
        }

    def verify(self) -> dict[str, Any]:
        project=self._load_project()
        spec=AcceptanceSpec.load(self._acceptance_path())
        snapshot=AcceptanceSnapshot.capture([self._acceptance_path()])
        refs=[r.path for r in self.evidence.list_refs(project.project_id)]
        self._emit_runtime("verification.started", "Independent verification started", project_id=project.project_id, source="verifier")
        report=Verifier(self.root).verify(spec, snapshot, refs)
        self.store.add_event(project.project_id, None, "project.verification", dataclass_to_jsonable(report))
        payload=dataclass_to_jsonable(report)
        self._emit_runtime("verification.finished", f"Independent verification {report.verdict.value}", project_id=project.project_id, payload={"status": report.verdict.value, "checks": payload.get("checks", []), "reasons": payload.get("reasons", [])}, severity="success" if report.verdict is Verdict.PASS else "error", source="verifier")
        return payload

    def deliver(self) -> str:
        project=self._load_project()
        status=self.status()
        status["verification"] = self.verify()
        status["evidence"] = [dataclass_to_jsonable(r) for r in self.evidence.list_refs(project.project_id)]
        status["task_results"] = status["tasks"]
        path = DeliveryManager(self.root, self.store).create(project.project_id, status)
        self.store.set_project_state(project.project_id, ProjectState.DELIVERED)
        self.store.add_event(project.project_id, None, "project.delivered", {"path": str(path)})
        self._emit_runtime("project.delivered", "Delivery package generated", project_id=project.project_id, payload={"path": str(path)}, severity="success")
        return str(path)

    def _execute_task(self, project: ProjectMap, task: TaskContract, agent: AgentSpec) -> dict[str, Any]:
        self._emit_runtime("task.started", task.goal, project_id=project.project_id, agent_id=agent.name, task_id=task.task_id, payload={"owner": agent.name, "complexity": task.complexity.value})
        verifier=Verifier(self.root)
        acceptance_path=self._task_acceptance_path(task)
        spec=AcceptanceSpec.load(acceptance_path)
        snapshot=AcceptanceSnapshot.capture([acceptance_path])
        baseline=verifier.verify(spec, snapshot, [])
        baseline_ref=self.evidence.add_text(project.project_id, task.task_id, "baseline", "baseline_verification.json", json.dumps(dataclass_to_jsonable(baseline), sort_keys=True))
        evidence_refs=[baseline_ref.path]
        if baseline.verdict is Verdict.PASS:
            self.store.set_task_state(task.task_id, TaskState.PASS)
            self.memory.record_agent_outcome(agent.name, True, False, 0)
            return {"task_id":task.task_id,"state":"PASS","iterations":0,"reason":"acceptance already passed"}

        if self.model_router is None:
            self.store.set_task_state(task.task_id, TaskState.BLOCKED)
            return {"task_id":task.task_id,"state":"BLOCKED","iterations":0,"reason":"no model provider configured"}

        tools=self._tools_for(agent, project.project_id, task.task_id)
        feedback=FeedbackLoop(max_cycles=self.max_feedback_cycles)
        context: dict[str, Any] = {
            "project": dataclass_to_jsonable(project),
            "baseline_verification": dataclass_to_jsonable(baseline),
            "memory": self.memory.retrieve(project.project_id, verified_only=True),
        }
        self.store.set_task_state(task.task_id, TaskState.IMPLEMENTATION)

        for iteration in range(1, self.max_task_iterations + 1):
            try:
                performance=self.memory.agent_performance(agent.name)
                routed_complexity=effective_complexity(task.complexity,performance)
                if routed_complexity is not task.complexity:
                    self.store.add_event(project.project_id,task.task_id,"model.escalated",{"from":task.complexity.value,"to":routed_complexity.value,"performance":performance})
                provider=self.model_router.route(routed_complexity)
                runtime=AgentRuntime(provider, tools)
                context["agent_messages"] = [
                    message for message in self.store.list_messages(project.project_id)
                    if message["recipient"] == agent.name and message.get("task_id") in {None, task.task_id}
                ]
                proposal=runtime.propose(agent, task, context)
            except (KeyError, AgentProtocolError, RuntimeError) as exc:
                self.store.add_event(project.project_id, task.task_id, "agent.protocol_error", {"error":str(exc),"iteration":iteration})
                if iteration >= self.max_task_iterations:
                    self.store.set_task_state(task.task_id, TaskState.BLOCKED)
                    return {"task_id":task.task_id,"state":"BLOCKED","iterations":iteration,"reason":str(exc)}
                context["feedback"] = f"Agent protocol/model failure: {exc}. Return valid structured output."
                continue

            proposal_ref=self.evidence.add_text(project.project_id, task.task_id, f"run-{iteration}", "proposal.json", json.dumps(dataclass_to_jsonable(proposal), sort_keys=True, default=str))
            evidence_refs.append(proposal_ref.path)

            if proposal.research_requests or proposal.status.upper() == "NEEDS_RESEARCH":
                try:
                    findings=self._resolve_research_requests(project,task,proposal.research_requests,iteration)
                except RuntimeError as exc:
                    self.store.set_task_state(task.task_id,TaskState.BLOCKED)
                    return {"task_id":task.task_id,"state":"BLOCKED","iterations":iteration,"reason":str(exc)}
                context["research_findings"] = findings
                continue

            if proposal.specialist_requests or proposal.status.upper() == "NEEDS_SPECIALIST":
                try:
                    advice=self._resolve_specialist_requests(project,task,proposal.specialist_requests,iteration)
                except (RuntimeError,AgentProtocolError,KeyError) as exc:
                    self.store.set_task_state(task.task_id,TaskState.BLOCKED)
                    return {"task_id":task.task_id,"state":"BLOCKED","iterations":iteration,"reason":f"specialist consultation failed: {exc}"}
                context["specialist_consultations"] = advice
                continue

            pre=feedback.evaluate(proposal, evidence_refs)
            self.store.add_event(project.project_id, task.task_id, "feedback.pre_execution", dataclass_to_jsonable(pre))
            if pre.blocked:
                self.store.set_task_state(task.task_id, TaskState.BLOCKED)
                return {"task_id":task.task_id,"state":"BLOCKED","iterations":iteration,"reason":"feedback cycle bound reached"}
            if pre.decision.value != "APPROVE_FOR_IMPLEMENTATION":
                if pre.decision.value == "REJECT_HYPOTHESIS":
                    self.memory.record_pattern(project.project_id, "rejected_hypothesis", {
                        "task_id": task.task_id,
                        "agent": agent.name,
                        "iteration": iteration,
                        "hypotheses": dataclass_to_jsonable(proposal.hypotheses),
                        "actions": dataclass_to_jsonable(proposal.actions),
                        "feedback": dataclass_to_jsonable(pre),
                    }, verified=False)
                context["feedback"] = dataclass_to_jsonable(pre)
                continue

            pending=self._approval_needed(proposal)
            if pending is not None:
                self.store.add_event(project.project_id,task.task_id,"approval.required",dataclass_to_jsonable(pending))
                self.store.set_task_state(task.task_id,TaskState.BLOCKED)
                return {"task_id":task.task_id,"state":"BLOCKED","iterations":iteration,"reason":f"approval required: {pending.approval_id} ({pending.risk_class})"}

            try:
                runtime.execute_actions(agent, proposal)
            except (SecurityError, PermissionError, FileNotFoundError, ValueError) as exc:
                self.store.add_event(project.project_id, task.task_id, "action.blocked", {"error":str(exc),"iteration":iteration})
                self.store.set_task_state(task.task_id, TaskState.BLOCKED)
                self.memory.record_agent_outcome(agent.name, False, False, iteration)
                return {"task_id":task.task_id,"state":"BLOCKED","iterations":iteration,"reason":str(exc)}

            execution_ref=self.evidence.add_text(project.project_id, task.task_id, f"run-{iteration}", "execution.json", json.dumps(proposal.raw.get("action_results", []), sort_keys=True, default=str))
            evidence_refs.append(execution_ref.path)
            context["last_tool_results"] = proposal.raw.get("action_results", [])
            post=feedback.evaluate(proposal, evidence_refs)
            self.store.add_event(project.project_id, task.task_id, "feedback.post_execution", dataclass_to_jsonable(post))
            if post.decision.value != "APPROVE_FOR_IMPLEMENTATION":
                if post.decision.value == "REJECT_HYPOTHESIS":
                    self.memory.record_pattern(project.project_id, "rejected_hypothesis", {
                        "task_id": task.task_id,
                        "agent": agent.name,
                        "iteration": iteration,
                        "hypotheses": dataclass_to_jsonable(proposal.hypotheses),
                        "actions": dataclass_to_jsonable(proposal.actions),
                        "feedback": dataclass_to_jsonable(post),
                    }, verified=False)
                context["feedback"] = dataclass_to_jsonable(post)
                continue

            if proposal.status.upper() == "CONTINUE" or self._actions_are_observational(proposal.actions):
                context["instruction"] = "Use the tool results above to continue diagnosis. Do not claim completion until a candidate implementation is ready for independent verification."
                continue

            self.store.set_task_state(task.task_id, TaskState.VERIFY)
            report=verifier.verify(spec, snapshot, evidence_refs)
            verification_ref=self.evidence.add_text(project.project_id, task.task_id, f"run-{iteration}", "verification.json", json.dumps(dataclass_to_jsonable(report), sort_keys=True))
            evidence_refs.append(verification_ref.path)
            if report.verdict is Verdict.PASS:
                self.store.set_task_state(task.task_id, TaskState.PASS)
                candidate=self.memory.record_pattern(project.project_id, "candidate_fix", {
                    "task_id":task.task_id,"agent":agent.name,"actions":dataclass_to_jsonable(proposal.actions),
                    "verification":dataclass_to_jsonable(report),
                }, verified=True)
                self.memory.promote_success(candidate)
                self.memory.record_agent_outcome(agent.name, True, False, iteration)
                return {"task_id":task.task_id,"state":"PASS","iterations":iteration,"verification":dataclass_to_jsonable(report)}
            self.memory.record_pattern(project.project_id, "failed_attempt", {
                "task_id": task.task_id,
                "agent": agent.name,
                "iteration": iteration,
                "actions": dataclass_to_jsonable(proposal.actions),
                "verification": dataclass_to_jsonable(report),
                "hypotheses": dataclass_to_jsonable(proposal.hypotheses),
            }, verified=False)
            context["feedback"] = {"verification":dataclass_to_jsonable(report),"instruction":"Previous candidate did not pass. Use evidence to form a new hypothesis; do not weaken gates."}
            self.store.set_task_state(task.task_id, TaskState.IMPLEMENTATION)

        self.store.set_task_state(task.task_id, TaskState.FAILED)
        self.memory.record_agent_outcome(agent.name, False, False, self.max_task_iterations)
        return {"task_id":task.task_id,"state":"FAILED","iterations":self.max_task_iterations,"reason":"iteration limit reached"}

    def _approval_needed(self, proposal):
        policy=self.approvals.policy()
        for action in proposal.actions:
            if action.tool not in {"shell","git"}:
                continue
            command=str(action.args.get("command",""))
            if action.tool=="git" and not command.startswith("git "):
                command="git "+command
            risk=classify_command(command)
            if risk != "low" and not policy.allows(command,risk):
                return self.approvals.request(command,risk,action.reason or "agent requested high-risk action")
        return None

    @staticmethod
    def _actions_are_observational(actions) -> bool:
        if not actions:
            return False
        return all(a.tool in {"filesystem.read","filesystem.search"} for a in actions)

    def _resolve_research_requests(self, project: ProjectMap, task: TaskContract, requests: list[dict[str, Any]], iteration: int) -> list[dict[str, Any]]:
        if not requests:
            raise RuntimeError("agent requested research but did not provide a research request")
        findings_out=[]
        for i,item in enumerate(requests,1):
            req=ResearchRequest(
                topic=str(item.get("topic","")), questions=[str(x) for x in item.get("questions",[])],
                reason=str(item.get("reason","needed by specialist")),
                preferred_sources=[str(x) for x in item.get("preferred_sources",[])] or None,
                freshness_days=int(item["freshness_days"]) if item.get("freshness_days") is not None else None,
            )
            findings=self.research_manager.research(req)
            payload=[dataclass_to_jsonable(f) for f in findings]
            ref=self.evidence.add_text(project.project_id,task.task_id,f"run-{iteration}",f"research-{i}.json",json.dumps(payload,sort_keys=True))
            findings_out.extend(payload)
            self.store.add_memory(project.project_id,"research",{"request":dataclass_to_jsonable(req),"findings":payload,"evidence":ref.path},verified=False)
            self.store.add_event(project.project_id,task.task_id,"research.completed",{"topic":req.topic,"findings":len(payload)})
        return findings_out

    def _resolve_specialist_requests(self, project: ProjectMap, task: TaskContract, requests: list[dict[str, Any]], iteration: int) -> list[dict[str, Any]]:
        if not requests:
            raise RuntimeError("agent requested a specialist but did not specify expertise")
        advice=[]
        agents=self._load_agents()
        for i,item in enumerate(requests,1):
            expertise=str(item.get("expertise","Domain")); reason=str(item.get("reason","requested by task owner"))
            specialist=self.factory.create_specialist(expertise,reason,write_scopes=[],tools=["filesystem.read","filesystem.search"])
            existing={a.name for a in agents}
            if specialist.name not in existing:
                agents.append(specialist); self._save_agents(agents)
            consult=TaskContract(
                task_id=f"{task.task_id}-CONSULT-{iteration}-{i}",project_id=project.project_id,
                goal=f"Provide read-only specialist advice for {task.task_id}: {task.goal}",owner=specialist.name,dependencies=[],
                read_scopes=["."],write_scopes=[],required_evidence=[],acceptance_criteria=["provide evidence-backed consultation"],
                prohibited_actions=specialist.forbidden_actions,complexity=Complexity.HIGH,risk=RiskLevel.LOW,
                metadata={"parent_task":task.task_id,"consultation":True},
            )
            provider=self.model_router.route(Complexity.HIGH) if self.model_router else None
            if provider is None: raise RuntimeError("no model provider configured for specialist consultation")
            registry=self._tools_for(specialist,project.project_id,task.task_id)
            report=AgentRuntime(provider,registry).propose(specialist,consult,{
                "project":dataclass_to_jsonable(project),"parent_task":dataclass_to_jsonable(task),"request":item
            })
            payload=dataclass_to_jsonable(report)
            ref=self.evidence.add_text(project.project_id,task.task_id,f"run-{iteration}",f"specialist-{i}.json",json.dumps(payload,sort_keys=True,default=str))
            advice.append(payload)
            self.store.add_event(project.project_id,task.task_id,"specialist.consulted",{"specialist":specialist.name,"evidence":ref.path})
        return advice

    def _fallback_plan(self, project: ProjectMap, agents: list[AgentSpec]) -> ProjectPlan:
        implementers=[a for a in agents if "testing" not in a.capabilities and a.write_scopes]
        if not implementers:
            implementers=[a for a in agents if a.write_scopes]
        if not implementers:
            raise RuntimeError("no implementation-capable specialist could be staffed")
        # Fail-safe fallback is a single accountable lead. Model-generated plans may later fan out into parallel domain tasks.
        lead=next((a for a in implementers if "software_engineering" in a.capabilities), implementers[0])
        task=TaskContract(
            task_id="T-001", project_id=project.project_id, goal=project.objective, owner=lead.name,
            dependencies=[], read_scopes=lead.read_scopes, write_scopes=lead.write_scopes,
            required_evidence=["baseline_verification","proposal","execution","verification"],
            acceptance_criteria=["all configured acceptance gates pass without modification"],
            prohibited_actions=list(set(lead.forbidden_actions + ["weaken tests", "modify .office acceptance snapshot"])),
            complexity=Complexity.MEDIUM, risk=RiskLevel.MEDIUM,
            metadata={"fallback_plan":True,"available_specialists":[a.name for a in agents]},
        )
        return ProjectPlan([task])

    def _tools_for(self, agent: AgentSpec, project_id: str, task_id: str) -> ToolRegistry:
        def audit(kind: str, data: dict[str, Any]) -> None:
            self.store.add_event(project_id, task_id, kind, data)
            summary = kind
            if kind == "file.read": summary = f"Read {data.get('path', '')}"
            elif kind == "file.written": summary = f"Wrote {data.get('path', '')}"
            elif kind.startswith("command."): summary = str(data.get("command") or kind)
            self._emit_runtime(kind, summary, project_id=project_id, agent_id=agent.name, task_id=task_id, payload=data, source="tool")
        permissions=PermissionSet(agent.read_scopes, agent.write_scopes, [])
        policy=self.approvals.policy()
        authorization = None
        if self.run_coordinator is not None:
            try:
                active_mode = self.run_coordinator.active().mode
                if active_mode in {"fast-audit", "check-report"}:
                    authorization = AuditModePolicy(active_mode).authorize
            except RuntimeError:
                pass
        registry=ToolRegistry(authorization=authorization)
        candidates = {
            "filesystem.read": FileReadTool(self.root, permissions, audit),
            "filesystem.search": FileSearchTool(self.root, permissions, audit),
            "filesystem.write": FileWriteTool(self.root, permissions, audit),
            "filesystem.replace_text": ReplaceTextTool(self.root, permissions, audit),
            "shell": ShellTool(self.root, permissions, policy, audit),
            "git": GitTool(self.root, permissions, policy, audit),
        }
        for name in agent.allowed_tools:
            if name in candidates:
                registry.register(candidates[name])
        return registry

    def _prepare_acceptance(self, project: ProjectMap) -> None:
        target=self._acceptance_path()
        source=self.root / "acceptance.json"
        if source.exists():
            shutil.copy2(source, target)
            return
        if project.metadata.get("has_tests") and "Python" in project.technologies:
            raw={"gates":[{"name":"pytest","command":"python -m pytest -q","expected_exit":0}],"required_evidence":[]}
        elif project.metadata.get("has_tests") and "Node.js" in project.technologies:
            raw={"gates":[{"name":"npm-test","command":"npm test","expected_exit":0}],"required_evidence":[]}
        else:
            raw={"gates":[{"name":"unconfigured","command":"python -c \"import sys; print('NO_ACCEPTANCE_CONFIGURED'); sys.exit(2)\"","expected_exit":0}],"required_evidence":[]}
        self._write_json(target, raw)

    def _acceptance_path(self) -> Path:
        return self.office_dir / "acceptance" / "project.json"

    def _task_acceptance_path(self, task: TaskContract) -> Path:
        specific=self.office_dir / "acceptance" / "tasks" / f"{task.task_id}.json"
        return specific if specific.exists() else self._acceptance_path()

    def _save_agents(self, agents: list[AgentSpec]) -> None:
        target=self.office_dir / "agents"
        for old in target.glob("*.json"): old.unlink()
        for i, agent in enumerate(agents, 1):
            slug=re.sub(r"[^a-z0-9]+","-",agent.name.lower()).strip("-")
            self._write_json(target / f"{i:02d}-{slug}.json", dataclass_to_jsonable(agent))

    def _load_agents(self) -> list[AgentSpec]:
        agents=[]
        for p in sorted((self.office_dir/"agents").glob("*.json")):
            d=json.loads(p.read_text()); d["model_tier"]=Complexity(d["model_tier"]); agents.append(AgentSpec(**d))
        return agents

    def _save_plan(self, plan: ProjectPlan) -> None:
        self._write_json(self.office_dir / "plan.json", {"tasks":[dataclass_to_jsonable(t) for t in plan.tasks]})

    def _load_plan(self) -> ProjectPlan:
        raw=json.loads((self.office_dir/"plan.json").read_text()); tasks=[]
        for d in raw["tasks"]:
            d["complexity"]=Complexity(d["complexity"]); d["risk"]=RiskLevel(d["risk"]); tasks.append(TaskContract(**d))
        return ProjectPlan(tasks)

    def _load_project(self) -> ProjectMap:
        p=self.office_dir/"project.json"
        if not p.exists(): raise RuntimeError("project has not been started; run office start first")
        return ProjectMap(**json.loads(p.read_text()))

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))
