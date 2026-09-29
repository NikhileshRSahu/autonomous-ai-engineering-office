import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from engineering_office.models import Complexity
from engineering_office.models_runtime import ModelProfile, ModelRouter, OpenAICompatibleProvider, ScriptedProvider


def test_scripted_provider_returns_queued_response():
    p = ScriptedProvider(["first", "second"])
    assert p.complete([{"role":"user","content":"x"}]).content == "first"
    assert p.complete([{"role":"user","content":"x"}]).content == "second"
    with pytest.raises(RuntimeError):
        p.complete([])


def test_router_maps_complexity_and_fails_closed():
    low = ScriptedProvider(["ok"])
    router = ModelRouter({Complexity.LOW: low})
    assert router.route(Complexity.LOW) is low
    with pytest.raises(KeyError):
        router.route(Complexity.HIGH)


def test_openai_compatible_provider_posts_expected_payload(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"choices":[{"message":{"content":"hello"}}],"usage":{"prompt_tokens":3,"completion_tokens":2}}).encode()
    def fake(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        captured["headers"] = dict(req.header_items())
        return Response()
    monkeypatch.setattr("engineering_office.models_runtime.urlopen", fake)
    profile = ModelProfile(name="local", endpoint="http://127.0.0.1:8080/v1", model="qwen", api_key_env=None)
    provider = OpenAICompatibleProvider(profile)
    resp = provider.complete([{"role":"user","content":"hi"}], response_format={"type":"json_object"})
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["model"] == "qwen"
    assert captured["body"]["response_format"] == {"type":"json_object"}
    assert resp.content == "hello"
    assert resp.usage["total_tokens"] == 5


def test_model_profile_secret_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("OFFICE_TEST_KEY", "secret-key")
    p = ModelProfile(name="x", endpoint="http://x/v1", model="m", api_key_env="OFFICE_TEST_KEY")
    assert p.api_key() == "secret-key"
    assert "secret-key" not in repr(p)


def test_config_can_build_jit_local_model_router(tmp_path):
    from engineering_office.cli import _router_from_config
    from engineering_office.config import OfficeConfig

    cfg_path = tmp_path / "local.json"
    cfg_path.write_text(json.dumps({
        "model_profiles": {
            "qwen_provider": {"endpoint":"http://127.0.0.1:8080/v1","model":"qwen-30b","timeout":900},
            "nemotron_provider": {"endpoint":"http://127.0.0.1:8081/v1","model":"nemotron-30b","timeout":900}
        },
        "routing": {"LOW":"qwen_provider","MEDIUM":"qwen_provider","HIGH":"nemotron_provider","ESCALATION":"nemotron_provider"},
        "local_models": {
            "qwen": {"endpoint":"http://127.0.0.1:8080/v1","expected_model":"qwen-30b","start_command":["llama-server","-m","/usb/qwen.gguf","--port","8080"],"startup_timeout":600},
            "nemotron": {"endpoint":"http://127.0.0.1:8081/v1","expected_model":"nemotron-30b","start_command":["llama-server","-m","/usb/nemotron.gguf","--port","8081"],"startup_timeout":600}
        },
        "model_bindings": {"LOW":"qwen","MEDIUM":"qwen","HIGH":"nemotron","ESCALATION":"nemotron"},
        "local_runtime_dir": ".office/runtime/models"
    }))

    cfg = OfficeConfig.load(cfg_path)
    assert cfg.local_models["qwen"].startup_timeout == 600
    router = _router_from_config(str(cfg_path), project_root=tmp_path)
    assert router is not None
    assert router.lifecycle_manager is not None
    assert router.model_key(Complexity.MEDIUM) == "qwen"
    assert router.model_key(Complexity.HIGH) == "nemotron"
    assert router.lifecycle_manager.runtime_dir == (tmp_path / ".office/runtime/models").resolve()
