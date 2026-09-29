from __future__ import annotations
import json
from dataclasses import dataclass
from importlib.resources import files


@dataclass(slots=True)
class Capability:
    name: str
    tools: list[str]
    write_scopes: list[str]


class CapabilityRegistry:
    def __init__(self, capabilities: dict[str, Capability]):
        self.capabilities = capabilities

    @classmethod
    def default(cls) -> "CapabilityRegistry":
        path = files("engineering_office").joinpath("data/capabilities.json")
        raw = json.loads(path.read_text())
        return cls({k: Capability(k, v["tools"], v["write"]) for k, v in raw.items()})

    def get(self, name: str) -> Capability:
        return self.capabilities[name]

    def has(self, name: str) -> bool:
        return name in self.capabilities
