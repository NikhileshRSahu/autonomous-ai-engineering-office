from __future__ import annotations

import json
from pathlib import Path


class AgentControlManager:
    """Persist per-agent execution state for the local Office runtime."""

    VALID = {"running", "paused", "halted"}

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}")

    def _read(self) -> dict[str, dict[str, str]]:
        try:
            raw = json.loads(self.path.read_text())
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, dict[str, str]] = {}
        for name, item in raw.items():
            state = item.get("state") if isinstance(item, dict) else None
            if state in self.VALID:
                out[str(name)] = {"state": str(state)}
        return out

    def _write(self, data: dict[str, dict[str, str]]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def state(self, agent_name: str) -> dict[str, str]:
        return self._read().get(agent_name, {"state": "running"})

    def all_states(self) -> dict[str, dict[str, str]]:
        return self._read()

    def set(self, agent_name: str, state: str) -> dict[str, str]:
        if state not in self.VALID:
            raise ValueError(f"invalid agent state: {state}")
        data = self._read()
        data[agent_name] = {"state": state}
        self._write(data)
        return data[agent_name]

    def pause(self, agent_name: str) -> dict[str, str]:
        return self.set(agent_name, "paused")

    def halt(self, agent_name: str) -> dict[str, str]:
        return self.set(agent_name, "halted")

    def resume(self, agent_name: str) -> dict[str, str]:
        return self.set(agent_name, "running")
