from __future__ import annotations
import json
from typing import Any

from .models import AgentReport, AgentSpec, Hypothesis, TaskContract, ToolAction
from .models_runtime import ModelProvider
from .prompts import build_agent_messages
from .tools import ToolRegistry


class AgentProtocolError(RuntimeError):
    pass


class AgentRuntime:
    REQUIRED_FIELDS = {"status","observations","interpretations","hypotheses","actions","tests","risks"}

    def __init__(self, provider: ModelProvider, tools: ToolRegistry):
        self.provider = provider
        self.tools = tools

    def propose(self, agent: AgentSpec, task: TaskContract, context: dict[str, Any]) -> AgentReport:
        response = self.provider.complete(build_agent_messages(agent, task, context), response_format={"type":"json_object"})
        raw = self._parse(response.content)
        report = self._to_report(raw)
        self._prevalidate_actions(agent, report.actions)
        report.raw["model_usage"] = response.usage
        return report

    def execute_actions(self, agent: AgentSpec, report: AgentReport) -> AgentReport:
        self._prevalidate_actions(agent, report.actions)
        action_results=[]
        for action in report.actions:
            result = self.tools.execute(action.tool, action.args)
            action_results.append({
                "tool": action.tool, "args": dict(action.args), "reason": action.reason,
                "ok": result.ok, "stdout": result.stdout[-5000:],
                "stderr": result.stderr[-5000:], "returncode": result.returncode, "data": result.data,
            })
        report.raw["action_results"] = action_results
        return report

    def run(self, agent: AgentSpec, task: TaskContract, context: dict[str, Any]) -> AgentReport:
        report = self.propose(agent, task, context)
        return self.execute_actions(agent, report)

    def _parse(self, content: str) -> dict[str, Any]:
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentProtocolError(f"model output is not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise AgentProtocolError("model output must be a JSON object")
        missing = self.REQUIRED_FIELDS - value.keys()
        if missing:
            raise AgentProtocolError(f"model output missing required field(s): {', '.join(sorted(missing))}")
        for key in ["observations","interpretations","hypotheses","actions","tests","risks"]:
            if not isinstance(value[key], list):
                raise AgentProtocolError(f"field {key} must be a list")
        return value

    def _to_report(self, raw: dict[str, Any]) -> AgentReport:
        try:
            hypotheses = [Hypothesis(**h) for h in raw.get("hypotheses", [])]
            actions = [ToolAction(tool=a["tool"], args=dict(a.get("args", {})), reason=str(a.get("reason", ""))) for a in raw.get("actions", [])]
        except (TypeError, KeyError, ValueError) as exc:
            raise AgentProtocolError(f"invalid structured agent report: {exc}") from exc
        return AgentReport(
            status=str(raw["status"]), observations=[str(x) for x in raw["observations"]],
            interpretations=[str(x) for x in raw["interpretations"]], hypotheses=hypotheses, actions=actions,
            tests=[str(x) for x in raw["tests"]], risks=[str(x) for x in raw["risks"]],
            specialist_requests=list(raw.get("specialist_requests", [])),
            research_requests=list(raw.get("research_requests", [])), handoff=str(raw.get("handoff", "")), raw=dict(raw),
        )

    def _prevalidate_actions(self, agent: AgentSpec, actions: list[ToolAction]) -> None:
        available = set(self.tools.names())
        allowed = set(agent.allowed_tools)
        for action in actions:
            if action.tool not in available:
                raise AgentProtocolError(f"unknown tool requested: {action.tool}")
            if action.tool not in allowed:
                raise AgentProtocolError(f"tool not allowed for agent {agent.name}: {action.tool}")
