from __future__ import annotations
from typing import Any
from .storage import OfficeStore


class MemoryManager:
    def __init__(self, store: OfficeStore):
        self.store = store

    def record_pattern(self, project_id: str | None, kind: str, data: dict[str, Any], verified: bool = False) -> int:
        return self.store.add_memory(project_id, kind, data, verified)

    def promote_success(self, memory_id: int) -> bool:
        item = self.store.get_memory(memory_id)
        if not item["verified"]:
            return False
        payload = dict(item["data"])
        payload["source_memory_id"] = memory_id
        self.store.add_memory(item["project_id"], "successful_fix", payload, True)
        return True

    def record_agent_outcome(self, agent_name: str, verified_success: bool, false_pass: bool, iterations: int) -> None:
        self.store.record_agent_outcome(agent_name, verified_success, false_pass, iterations)

    def record_agent_skill(self, agent_name: str, tag: str, strong: bool) -> int:
        kind = "agent_strength" if strong else "agent_weakness"
        return self.store.add_memory(None, kind, {"agent_name": agent_name, "tag": tag}, True)

    def agent_performance(self, agent_name: str) -> dict[str, Any]:
        raw = self.store.get_agent_metrics(agent_name)
        tasks = raw["tasks"]
        all_memory = self.store.list_memory(None, verified_only=True)
        strengths = sorted({m["data"].get("tag") for m in all_memory if m["kind"] == "agent_strength" and m["data"].get("agent_name") == agent_name and m["data"].get("tag")})
        weaknesses = sorted({m["data"].get("tag") for m in all_memory if m["kind"] == "agent_weakness" and m["data"].get("agent_name") == agent_name and m["data"].get("tag")})
        return raw | {
            "verified_success_rate": raw["verified_successes"] / tasks if tasks else 0.0,
            "false_pass_rate": raw["false_passes"] / tasks if tasks else 0.0,
            "strengths": strengths,
            "weaknesses": weaknesses,
        }

    def retrieve(self, project_id: str | None = None, verified_only: bool = True, kinds: set[str] | None = None) -> list[dict[str, Any]]:
        items = self.store.list_memory(project_id, verified_only=verified_only)
        if kinds:
            items = [m for m in items if m["kind"] in kinds]
        return items
