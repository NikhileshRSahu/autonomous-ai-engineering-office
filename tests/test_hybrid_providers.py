from __future__ import annotations

import json
from pathlib import Path

import pytest

from engineering_office.models import Complexity
from engineering_office.models_runtime import ModelResponse
from engineering_office.privacy import PrivacySanitizer
from engineering_office.providers import HybridFallbackProvider


class Stub:
    def __init__(self, name, *, fail=False):
        self.name=name; self.fail=fail; self.calls=[]
    def complete(self, messages, response_format=None):
        self.calls.append(messages)
        if self.fail: raise RuntimeError(f"{self.name} failed")
        return ModelResponse(self.name, raw={"provider": self.name, "model": self.name})


def test_privacy_sanitizer_reuses_strong_secret_redaction(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-abcdefghijklmnopqrstuvwxyz1234567890")
    text = """Authorization: Bearer secretbearer123\npassword=hunter2\nsk-or-abcdefghijklmnopqrstuvwxyz1234567890\n-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"""
    out = PrivacySanitizer.redact_secrets(text)
    assert "hunter2" not in out
    assert "secretbearer123" not in out
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in out
    assert "BEGIN PRIVATE KEY" not in out


def test_hybrid_routine_is_local_first_then_cloud(monkeypatch):
    local=Stub("local", fail=True); cloud=Stub("cloud")
    provider=HybridFallbackProvider(local, is_review=False, cloud_providers=[cloud])
    result=provider.complete([{"role":"user","content":"x"}])
    assert result.content == "cloud"
    assert len(local.calls)==1 and len(cloud.calls)==1


def test_hybrid_review_is_cloud_first_then_local():
    local=Stub("local"); cloud=Stub("cloud")
    provider=HybridFallbackProvider(local, is_review=True, cloud_providers=[cloud])
    result=provider.complete([{"role":"user","content":"x"}])
    assert result.content == "cloud"
    assert len(cloud.calls)==1 and len(local.calls)==0


def test_hybrid_fails_cleanly_when_no_provider_is_available():
    provider=HybridFallbackProvider(None, is_review=True, cloud_providers=[])
    with pytest.raises(RuntimeError, match="no model provider completed"):
        provider.complete([{"role":"user","content":"x"}])


def test_cli_router_honors_configured_routing(tmp_path: Path, monkeypatch):
    from engineering_office.cli import _router_from_config
    from engineering_office.models_runtime import OpenAICompatibleProvider

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg=tmp_path/"cfg.json"
    cfg.write_text(json.dumps({
        "model_profiles": {
            "q": {"endpoint":"http://127.0.0.1:8080/v1","model":"qwen"},
            "n": {"endpoint":"http://127.0.0.1:8081/v1","model":"nemotron"},
        },
        "routing": {"LOW":"q","MEDIUM":"q","HIGH":"n","ESCALATION":"n"}
    }))
    router=_router_from_config(str(cfg), project_root=tmp_path)
    low=router.providers[Complexity.LOW]
    high=router.providers[Complexity.HIGH]
    assert isinstance(low, HybridFallbackProvider)
    assert isinstance(high, HybridFallbackProvider)
    assert isinstance(low.local_provider, OpenAICompatibleProvider)
    assert low.local_provider.profile.model == "qwen"
    assert high.local_provider.profile.model == "nemotron"
    assert low.is_review is False
    assert high.is_review is True


def test_user_env_does_not_override_explicit_environment(tmp_path: Path, monkeypatch):
    import engineering_office.config as config
    env=tmp_path/".env"
    env.write_text("OPENROUTER_API_KEY=file-value\nGROQ_API_KEY=file-groq\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "process-value")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    config.load_user_env(env)
    assert __import__('os').environ["OPENROUTER_API_KEY"] == "process-value"
    assert __import__('os').environ["GROQ_API_KEY"] == "file-groq"


def test_cli_can_build_cloud_only_router_from_environment(monkeypatch):
    from engineering_office.cli import _router_from_config
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    router=_router_from_config(None)
    assert router is not None
    assert isinstance(router.providers[Complexity.LOW], HybridFallbackProvider)
    assert router.providers[Complexity.LOW].local_provider is None
    assert router.providers[Complexity.HIGH].is_review is True


def test_dashboard_service_uses_same_hybrid_router_as_cli(tmp_path: Path, monkeypatch):
    from engineering_office.office import OfficeEngine
    from engineering_office.ui_service import DashboardService
    OfficeEngine(tmp_path).start("inspect project")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    service=DashboardService(tmp_path)
    router=service.engine.model_router
    assert router is not None
    assert isinstance(router.providers[Complexity.LOW], HybridFallbackProvider)
    assert router.providers[Complexity.LOW].local_provider is None


def test_review_hybrid_defers_local_lifecycle_until_fallback():
    from engineering_office.models_runtime import ModelRouter
    class Manager:
        def __init__(self): self.calls=[]
        def ensure(self, name): self.calls.append(name)
    local=Stub("local")
    cloud=Stub("cloud")
    hybrid=HybridFallbackProvider(local, is_review=True, cloud_providers=[cloud], local_prepare=lambda: None)
    manager=Manager()
    router=ModelRouter({Complexity.HIGH:hybrid}, lifecycle_manager=manager, model_bindings={Complexity.HIGH:"nemotron"})
    routed=router.route(Complexity.HIGH)
    assert routed is hybrid
    assert manager.calls == []
    assert router.model_key(Complexity.HIGH) == "nemotron"


def test_openrouter_explicit_model_must_be_verified_zero_price(monkeypatch):
    import engineering_office.providers as providers
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "vendor/paid-model")

    def fake_request(url, **kwargs):
        assert url.endswith("/models")
        return {"data": [{"id": "vendor/paid-model", "pricing": {"prompt": "0.001", "completion": "0.002"}}]}

    monkeypatch.setattr(providers, "_request_json", fake_request)
    client = providers.OpenRouterClient()
    with pytest.raises(providers.ProviderUnavailable, match="not verified zero-price"):
        client._ensure_model()


def test_zero_cost_hybrid_skips_unverified_free_tier_clouds(monkeypatch):
    from engineering_office.providers import CloudProvider

    class UnverifiedCloud(Stub):
        configured = True
        zero_cost_verified = False

    local = Stub("local", fail=True)
    cloud = UnverifiedCloud("cloud")
    provider = HybridFallbackProvider(local, is_review=False, cloud_providers=[cloud])
    with pytest.raises(RuntimeError, match="no model provider completed"):
        provider.complete([{"role": "user", "content": "x"}])
    assert len(cloud.calls) == 0


def test_zero_cost_hybrid_can_opt_in_unverified_free_tier(monkeypatch):
    class UnverifiedCloud(Stub):
        configured = True
        zero_cost_verified = False

    monkeypatch.setenv("OFFICE_ALLOW_UNVERIFIED_FREE_TIER", "1")
    local = Stub("local", fail=True)
    cloud = UnverifiedCloud("cloud")
    provider = HybridFallbackProvider(local, is_review=False, cloud_providers=[cloud])
    result = provider.complete([{"role": "user", "content": "x"}])
    assert result.content == "cloud"
    assert len(cloud.calls) == 1


def test_cloud_status_exposes_zero_cost_eligibility(monkeypatch):
    import engineering_office.providers as providers
    monkeypatch.setenv("GROQ_API_KEY", "key")
    client = providers.GroqClient()
    status = client.status()
    assert status["configured"] is True
    assert status["zero_cost_verified"] is False
    assert status["zero_cost_eligible"] is False


def test_cli_router_blocks_routine_cloud_source_fallback_by_default(tmp_path: Path, monkeypatch):
    from engineering_office.cli import _router_from_config
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OFFICE_ALLOW_CLOUD_SOURCE_SNIPPETS", raising=False)
    router = _router_from_config(None, project_root=tmp_path)
    assert router is not None
    assert router.providers[Complexity.LOW].cloud_allowed is False
    assert router.providers[Complexity.MEDIUM].cloud_allowed is False
    assert router.providers[Complexity.HIGH].cloud_allowed is True
    assert router.providers[Complexity.ESCALATION].cloud_allowed is True


def test_routine_provider_does_not_send_to_cloud_when_cloud_not_allowed():
    local = Stub("local", fail=True)
    cloud = Stub("cloud")
    provider = HybridFallbackProvider(local, is_review=False, cloud_providers=[cloud], cloud_allowed=False)
    with pytest.raises(RuntimeError, match="no model provider completed"):
        provider.complete([{"role":"user","content":"PRIVATE SOURCE"}])
    assert len(cloud.calls) == 0
