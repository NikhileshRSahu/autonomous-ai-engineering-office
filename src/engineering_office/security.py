from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re


class SecurityError(RuntimeError):
    pass


@dataclass(slots=True)
class PermissionSet:
    read_scopes: list[str] = field(default_factory=lambda: ["."])
    write_scopes: list[str] = field(default_factory=list)
    approved_risks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ApprovalPolicy:
    auto_mode: bool = False
    approved_actions: set[str] = field(default_factory=set)
    approved_risk_classes: set[str] = field(default_factory=set)

    def allows(self, action: str, risk_class: str) -> bool:
        if risk_class == "low":
            return True
        return action in self.approved_actions or risk_class in self.approved_risk_classes


class PathGuard:
    PROTECTED_WRITE_ROOTS = {".office", ".git"}

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def resolve(self, relative: str, scopes: list[str], for_write: bool = False) -> Path:
        candidate = (self.root / relative).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise SecurityError(f"path escapes project root: {relative}") from exc
        # Existing parents may contain symlinks resolving outside; resolve(strict=False) already follows them.
        if for_write:
            rel_parts = candidate.relative_to(self.root).parts
            if rel_parts and rel_parts[0] in self.PROTECTED_WRITE_ROOTS:
                raise SecurityError(f"protected internal path cannot be modified by candidate tools: {relative}")
        if not self._in_scopes(candidate, scopes):
            kind = "write" if for_write else "read"
            raise SecurityError(f"{kind} path outside allowed scopes: {relative}")
        return candidate

    def _in_scopes(self, candidate: Path, scopes: list[str]) -> bool:
        if not scopes:
            return False
        for scope in scopes:
            scope_path = (self.root / scope).resolve(strict=False)
            try:
                scope_path.relative_to(self.root)
                candidate.relative_to(scope_path)
                return True
            except ValueError:
                continue
        return False


_HIGH_RISK_PATTERNS: list[tuple[str, str]] = [
    (r"\bgit\s+push\b", "external_publish"),
    (r"\b(?:kubectl|helm)\b.*\b(?:delete|apply|upgrade)\b", "deployment"),
    (r"\b(?:terraform)\b.*\b(?:apply|destroy)\b", "deployment"),
    (r"\b(?:rm\s+-rf|del\s+/[sq])\b", "destructive"),
    (r"\b(?:sudo|su)\b", "privileged"),
    (r"\b(?:DROP\s+DATABASE|TRUNCATE\s+TABLE)\b", "destructive_data"),
    (r"\b(?:npm\s+publish|twine\s+upload|docker\s+push)\b", "external_publish"),
    (r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash)", "remote_code_execution"),
]


def classify_command(command: str) -> str:
    for pattern, risk in _HIGH_RISK_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return risk
    return "low"


def redact_runtime_value(value):
    """Recursively redact secrets in runtime-observability payloads."""
    from .evidence import redact_secrets

    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {str(k): redact_runtime_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_runtime_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_runtime_value(v) for v in value)
    return value
