from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol, Any
import json
import shlex
import subprocess


@dataclass(slots=True)
class ResearchRequest:
    topic: str
    questions: list[str]
    reason: str
    preferred_sources: list[str] | None = None
    freshness_days: int | None = None


@dataclass(slots=True)
class ResearchFinding:
    finding: str
    source: str
    confidence: float
    applicability: str
    limitations: str
    implementation_notes: str = ""


class ResearchProvider(Protocol):
    def research(self, request: ResearchRequest) -> list[ResearchFinding]: ...


class CommandResearchProvider:
    """Adapter for an external search/browser program. JSON request on stdin, JSON findings on stdout."""
    def __init__(self, command: str, timeout: int = 180):
        self.command = command
        self.timeout = timeout

    def research(self, request: ResearchRequest) -> list[ResearchFinding]:
        proc = subprocess.run(
            shlex.split(self.command), input=json.dumps(asdict(request)), text=True,
            capture_output=True, timeout=self.timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"research provider failed: {proc.stderr.strip()}")
        raw=json.loads(proc.stdout)
        if not isinstance(raw, list):
            raise RuntimeError("research provider must return a JSON list")
        return [ResearchFinding(**item) for item in raw]


class ResearchManager:
    def __init__(self, provider: ResearchProvider | None):
        self.provider=provider

    def research(self, request: ResearchRequest) -> list[ResearchFinding]:
        if self.provider is None:
            raise RuntimeError("no research provider configured; research was not performed")
        return self.provider.research(request)
