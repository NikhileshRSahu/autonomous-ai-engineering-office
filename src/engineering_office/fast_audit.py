from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any
import re

from .project_index import IndexUpdate


@dataclass(slots=True)
class FastAuditPlan:
    stages: list[str]
    actions: list[str]
    skipped: dict[str, str] = field(default_factory=dict)
    model_phase_budget: dict[str, int] = field(default_factory=lambda: {"qwen": 1, "nemotron": 1, "qwen_followup": 1})


class FastAuditPlanner:
    def plan(self, index_update: IndexUpdate, *, simulation_requested: bool = False) -> FastAuditPlan:
        actions = ["incremental_index", "static_analysis", "cheap_validation", "targeted_tests", "consolidated_review", "report"]
        skipped: dict[str, str] = {}
        if simulation_requested:
            actions.insert(-2, "full_simulation")
        else:
            skipped["full_simulation"] = "Fast Audit skips expensive full simulation unless requested or required by the audit objective."
        return FastAuditPlan(
            stages=["IMPORT", "INDEX", "ANALYZE", "TEST", "REVIEW", "REPORT"],
            actions=actions,
            skipped=skipped,
        )


class AuditModePolicy:
    READ_ONLY_GIT = ("status", "diff", "log", "show", "rev-parse", "branch --show-current", "ls-files")
    SAFE_SHELL_PREFIXES = (
        "python -m pytest", "python3 -m pytest", "pytest ", "python -m unittest", "python3 -m unittest",
        "colcon build", "colcon test", "ctest", "cmake ", "ninja", "make", "npm test", "npm run test",
        "cargo test", "go test", "ros2 ", "gz ", "ign ",
    )
    MUTATION_PATTERNS = (
        r"(^|[;&|]\s*)rm\b", r"(^|[;&|]\s*)mv\b", r"(^|[;&|]\s*)cp\b", r"(^|[;&|]\s*)touch\b",
        r"(^|[;&|]\s*)mkdir\b", r"sed\s+-i\b", r"perl\s+-pi\b", r"(^|\s)(>|>>)\s*[^&]", r"\btee\b",
        r"git\s+(?:commit|push|checkout|switch|reset|restore|clean|merge|rebase|cherry-pick|tag)\b",
    )

    def __init__(self, mode: str = "fast-audit"):
        self.mode = mode

    @property
    def read_only(self) -> bool:
        return self.mode in {"fast-audit", "check-report"}

    @staticmethod
    def _office_path(path: str) -> bool:
        parts = PurePosixPath(str(path).replace("\\", "/")).parts
        return bool(parts) and parts[0] == ".office"

    def authorize(self, tool_name: str, args: dict[str, Any]) -> tuple[bool, str | None]:
        if not self.read_only:
            return True, None
        if tool_name in {"filesystem.read", "filesystem.search"}:
            return True, None
        if tool_name in {"filesystem.write", "filesystem.replace_text"}:
            path = str(args.get("path", ""))
            return (True, None) if self._office_path(path) else (False, "audit mode is read-only outside .office")
        if tool_name == "git":
            command = str(args.get("command", "")).strip()
            command = command[4:].strip() if command.startswith("git ") else command
            return (True, None) if any(command == prefix or command.startswith(prefix + " ") for prefix in self.READ_ONLY_GIT) else (False, "audit mode permits only read-only git commands")
        if tool_name == "shell":
            command = str(args.get("command", "")).strip()
            if any(re.search(pattern, command, re.I) for pattern in self.MUTATION_PATTERNS):
                return False, "audit mode rejected a mutating shell command"
            if command.startswith(self.SAFE_SHELL_PREFIXES):
                return True, None
            return False, "audit mode shell command is not in the safe build/test/simulation allowlist"
        return False, f"audit mode does not authorize tool {tool_name}"
