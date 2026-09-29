from __future__ import annotations

import os
from pathlib import Path

from .config import OfficeConfig, load_user_env
from .models import Complexity
from .models_runtime import LocalModelManager, ModelRouter, OpenAICompatibleProvider
from .providers import HybridFallbackProvider


def build_model_router(
    config_path: str | Path | None,
    *,
    project_root: str | Path | None = None,
) -> ModelRouter | None:
    """Build the same hybrid model router for CLI and Control Room.

    Explicit config drives local/model-profile routing. User-level API-key
    environment enables cloud fallback even when no model-config JSON exists.
    """
    load_user_env()
    cfg = OfficeConfig.load(config_path) if config_path else OfficeConfig()

    profile_providers = {
        name: OpenAICompatibleProvider(profile)
        for name, profile in cfg.model_profiles.items()
    }
    base_routed = {
        complexity: profile_providers[name]
        for complexity, name in cfg.routing.items()
        if name in profile_providers
    }

    manager = None
    if cfg.local_models:
        runtime = Path(cfg.local_runtime_dir).expanduser()
        if not runtime.is_absolute():
            if project_root is not None:
                base = Path(project_root).resolve()
            elif config_path is not None:
                base = Path(config_path).resolve().parent
            else:
                base = Path.cwd().resolve()
            runtime = (base / runtime).resolve()
        manager = LocalModelManager(cfg.local_models, runtime)

    cloud_configured = any(
        os.environ.get(key)
        for key in (
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GROQ_API_KEY",
        )
    )
    if not base_routed and not cloud_configured:
        return None

    routed = {}
    effective_bindings = dict(cfg.model_bindings)
    for complexity in Complexity:
        local_provider = base_routed.get(complexity)
        if local_provider is None and not cloud_configured:
            continue

        is_review = complexity in {Complexity.HIGH, Complexity.ESCALATION}
        binding = cfg.model_bindings.get(complexity)
        local_prepare = None
        if manager is not None and binding and is_review:
            # High-complexity review is cloud-first. Only prepare the configured
            # local reviewer if cloud options actually fail.
            local_prepare = lambda name=binding: manager.ensure(name)

        allow_source_cloud = os.environ.get("OFFICE_ALLOW_CLOUD_SOURCE_SNIPPETS", "").strip().lower() in {"1", "true", "yes", "on"}
        cloud_allowed = is_review or allow_source_cloud
        routed[complexity] = HybridFallbackProvider(
            local_provider,
            is_review=is_review,
            local_prepare=local_prepare,
            cloud_allowed=cloud_allowed,
        )

    return ModelRouter(
        routed,
        lifecycle_manager=manager,
        model_bindings=effective_bindings,
    )
