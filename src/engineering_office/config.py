from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
from .models import Complexity
from .models_runtime import LocalModelSpec, ModelProfile

import os


def load_user_env(path: str | Path | None = None) -> dict[str, str]:
    """Load optional per-user secrets without overriding process environment.

    Explicit environment variables always win over ~/.engineering-office/.env.
    The returned mapping contains only variable names and loaded values; callers
    should never log it.
    """
    env_path = Path(path).expanduser() if path is not None else Path("~/.engineering-office/.env").expanduser()
    loaded: dict[str, str] = {}
    if not env_path.is_file():
        return loaded
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0:1] == value[-1:] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded



@dataclass(slots=True)
class OfficeConfig:
    model_profiles: dict[str, ModelProfile] = field(default_factory=dict)
    routing: dict[Complexity, str] = field(default_factory=dict)
    local_models: dict[str, LocalModelSpec] = field(default_factory=dict)
    model_bindings: dict[Complexity, str] = field(default_factory=dict)
    local_runtime_dir: str = ".office/runtime/models"
    max_feedback_cycles: int = 4
    max_task_iterations: int = 6
    parallelism: int = 2
    intake_workspace_root: str = "~/.engineering-office/workspaces"
    intake_staging_root: str = "~/.engineering-office/staging"
    intake_max_files: int = 100_000
    intake_max_bytes: int = 8 * 1024 * 1024 * 1024
    intake_session_ttl: int = 24 * 60 * 60
    default_run_mode: str = "complete"
    fast_audit_max_context_files: int = 30
    fast_audit_max_context_chars: int = 200_000

    @classmethod
    def load(cls, path: str | Path) -> "OfficeConfig":
        raw = json.loads(Path(path).read_text())
        profiles = {name: ModelProfile(name=name, **cfg) for name, cfg in raw.get("model_profiles", {}).items()}
        routing = {Complexity(k): v for k, v in raw.get("routing", {}).items()}
        local_models = {name: LocalModelSpec(name=name, **cfg) for name, cfg in raw.get("local_models", {}).items()}
        model_bindings = {Complexity(k): v for k, v in raw.get("model_bindings", {}).items()}
        return cls(
            model_profiles=profiles, routing=routing,
            local_models=local_models, model_bindings=model_bindings,
            local_runtime_dir=str(raw.get("local_runtime_dir", ".office/runtime/models")),
            max_feedback_cycles=int(raw.get("max_feedback_cycles", 4)),
            max_task_iterations=int(raw.get("max_task_iterations", 6)),
            parallelism=int(raw.get("parallelism", 2)),
            intake_workspace_root=str(raw.get("intake_workspace_root", "~/.engineering-office/workspaces")),
            intake_staging_root=str(raw.get("intake_staging_root", "~/.engineering-office/staging")),
            intake_max_files=int(raw.get("intake_max_files", 100_000)),
            intake_max_bytes=int(raw.get("intake_max_bytes", 8 * 1024 * 1024 * 1024)),
            intake_session_ttl=int(raw.get("intake_session_ttl", 24 * 60 * 60)),
            default_run_mode=str(raw.get("default_run_mode", "complete")),
            fast_audit_max_context_files=int(raw.get("fast_audit_max_context_files", 30)),
            fast_audit_max_context_chars=int(raw.get("fast_audit_max_context_chars", 200_000)),
        )
