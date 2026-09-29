from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .models_runtime import ModelResponse
from .privacy import PrivacySanitizer


class ProviderUnavailable(RuntimeError):
    pass


def _request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        headers=headers or {},
        data=data,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8"))
    if not isinstance(raw, dict):
        raise ProviderUnavailable("provider returned a non-object JSON response")
    return raw


class CloudProvider:
    name = "cloud"

    def __init__(self, key_env: str, *, timeout: float = 60.0):
        self.key_env = key_env
        self.timeout = float(timeout)
        self.latency = 0.0
        self.calls = 0
        self.quota_status = "Available" if self.key else "Not Configured"
        self.selected_model: str | None = None
        # Only providers that can prove zero-price execution are eligible by
        # default.  Free-tier providers whose billing state cannot be queried
        # require an explicit user opt-in.
        self.zero_cost_verified = False
        self.zero_cost_policy = "unverified-free-tier"

    @property
    def key(self) -> str:
        return os.environ.get(self.key_env, "")

    @property
    def configured(self) -> bool:
        return bool(self.key)

    @property
    def zero_cost_eligible(self) -> bool:
        if self.zero_cost_policy == "verified-at-call":
            return True
        if self.zero_cost_verified:
            return True
        return os.environ.get("OFFICE_ALLOW_UNVERIFIED_FREE_TIER", "").strip().lower() in {"1", "true", "yes", "on"}

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "configured": self.configured,
            "model": self.selected_model,
            "quota_status": self.quota_status,
            "calls": self.calls,
            "latency_seconds": round(self.latency, 3),
            "zero_cost_verified": bool(self.zero_cost_verified),
            "zero_cost_eligible": bool(self.zero_cost_eligible),
            "zero_cost_policy": self.zero_cost_policy,
        }

    def complete(self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None) -> ModelResponse:
        raise NotImplementedError

    def _http_error(self, exc: urllib.error.HTTPError) -> ProviderUnavailable:
        if exc.code in {402, 429}:
            self.quota_status = "Quota Exhausted"
        return ProviderUnavailable(f"{self.name} request failed with HTTP {exc.code}")


class OpenRouterClient(CloudProvider):
    name = "OpenRouter"

    def __init__(self, *, timeout: float = 60.0):
        super().__init__("OPENROUTER_API_KEY", timeout=timeout)
        self.selected_model = os.environ.get("OPENROUTER_MODEL") or None
        self.zero_cost_policy = "verified-at-call"
        self._validated_model: str | None = None

    @staticmethod
    def _is_free(row: dict[str, Any]) -> bool:
        pricing = row.get("pricing") or {}
        try:
            return float(pricing.get("prompt", 1)) == 0.0 and float(pricing.get("completion", 1)) == 0.0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _score_model(model_id: str) -> tuple[int, str]:
        name = model_id.lower()
        score = 0
        for token, weight in (("coder", 8), ("qwen", 7), ("nemotron", 7), ("deepseek", 6), ("glm", 5), ("120b", 4), ("70b", 3), (":free", 2)):
            if token in name:
                score += weight
        return (-score, model_id)

    def _ensure_model(self) -> str:
        if not self.key:
            raise ProviderUnavailable("OpenRouter is not configured")
        if self.selected_model and self._validated_model == self.selected_model:
            return self.selected_model
        headers = {"Authorization": f"Bearer {self.key}"}
        try:
            raw = _request_json("https://openrouter.ai/api/v1/models", headers=headers, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        all_rows = [row for row in raw.get("data", []) if isinstance(row, dict)]
        if self.selected_model:
            row = next((item for item in all_rows if str(item.get("id", "")) == self.selected_model), None)
            if row is None or not self._is_free(row):
                raise ProviderUnavailable(f"OpenRouter model {self.selected_model} is not verified zero-price")
            self._validated_model = self.selected_model
            self.zero_cost_verified = True
            return self.selected_model
        rows = [row for row in all_rows if self._is_free(row)]
        if not rows:
            raise ProviderUnavailable("OpenRouter has no discoverable zero-price model")
        self.selected_model = sorted((str(row.get("id", "")) for row in rows if row.get("id")), key=self._score_model)[0]
        self._validated_model = self.selected_model
        self.zero_cost_verified = True
        return self.selected_model

    def complete(self, messages, response_format=None) -> ModelResponse:
        model = self._ensure_model()
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if response_format is not None:
            payload["response_format"] = response_format
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        started = time.monotonic()
        try:
            raw = _request_json("https://openrouter.ai/api/v1/chat/completions", headers=headers, payload=payload, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        self.calls += 1; self.latency = time.monotonic() - started
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable("OpenRouter response missing choices[0].message.content") from exc
        usage = raw.get("usage") or {}
        return ModelResponse(str(content), usage=dict(usage), raw={"provider": self.name, "model": model, "response": raw})


class GroqClient(CloudProvider):
    name = "Groq"

    def __init__(self, *, timeout: float = 60.0):
        super().__init__("GROQ_API_KEY", timeout=timeout)
        self.selected_model = os.environ.get("GROQ_MODEL") or None

    def _ensure_model(self) -> str:
        if self.selected_model:
            return self.selected_model
        if not self.key:
            raise ProviderUnavailable("Groq is not configured")
        try:
            raw = _request_json("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {self.key}"}, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        ids = [str(row.get("id")) for row in raw.get("data", []) if isinstance(row, dict) and row.get("id")]
        if not ids:
            raise ProviderUnavailable("Groq returned no available models")
        preferred = sorted(ids, key=lambda m: (0 if any(x in m.lower() for x in ("qwen", "llama", "gpt-oss")) else 1, m))
        self.selected_model = preferred[0]
        return self.selected_model

    def complete(self, messages, response_format=None) -> ModelResponse:
        model = self._ensure_model()
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if response_format is not None:
            payload["response_format"] = response_format
        started = time.monotonic()
        try:
            raw = _request_json(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                payload=payload,
                timeout=self.timeout,
            )
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        self.calls += 1; self.latency = time.monotonic() - started
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable("Groq response missing choices[0].message.content") from exc
        return ModelResponse(str(content), usage=dict(raw.get("usage") or {}), raw={"provider": self.name, "model": model, "response": raw})


class GeminiClient(CloudProvider):
    name = "Gemini"

    def __init__(self, *, timeout: float = 60.0):
        # Prefer GEMINI_API_KEY; GOOGLE_API_KEY is supported as a compatibility fallback.
        key_env = "GEMINI_API_KEY" if os.environ.get("GEMINI_API_KEY") else "GOOGLE_API_KEY"
        super().__init__(key_env, timeout=timeout)
        self.selected_model = os.environ.get("GEMINI_MODEL") or None

    def _ensure_model(self) -> str:
        if self.selected_model:
            return self.selected_model.removeprefix("models/")
        if not self.key:
            raise ProviderUnavailable("Gemini is not configured")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.key}"
        try:
            raw = _request_json(url, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        candidates = []
        for row in raw.get("models", []):
            if not isinstance(row, dict):
                continue
            methods = row.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            name = str(row.get("name", "")).removeprefix("models/")
            if name:
                candidates.append(name)
        if not candidates:
            raise ProviderUnavailable("Gemini returned no generateContent model")
        candidates.sort(key=lambda m: (0 if "flash" in m.lower() else 1, 0 if "latest" in m.lower() else 1, m))
        self.selected_model = candidates[0]
        return self.selected_model

    def complete(self, messages, response_format=None) -> ModelResponse:
        model = self._ensure_model()
        prompt = "\n\n".join(f"{m.get('role','user').upper()}: {m.get('content','')}" for m in messages)
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.key}"
        started = time.monotonic()
        try:
            raw = _request_json(url, headers={"Content-Type": "application/json"}, payload=payload, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        self.calls += 1; self.latency = time.monotonic() - started
        try:
            content = raw["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable("Gemini response missing candidates[0].content.parts[0].text") from exc
        usage_meta = raw.get("usageMetadata") or {}
        usage = {
            "prompt_tokens": int(usage_meta.get("promptTokenCount", 0) or 0),
            "completion_tokens": int(usage_meta.get("candidatesTokenCount", 0) or 0),
            "total_tokens": int(usage_meta.get("totalTokenCount", 0) or 0),
        }
        return ModelResponse(str(content), usage=usage, raw={"provider": self.name, "model": model, "response": raw})


class HybridFallbackProvider:
    """Local-first for routine work, cloud-first for review/escalation."""

    def __init__(
        self,
        local_provider,
        is_review: bool = False,
        *,
        cloud_providers: list[Any] | None = None,
        local_prepare=None,
        cloud_allowed: bool = True,
    ):
        self.local_provider = local_provider
        self.is_review = bool(is_review)
        self.defer_lifecycle = self.is_review
        self.cloud_providers = list(cloud_providers) if cloud_providers is not None else [OpenRouterClient(), GeminiClient(), GroqClient()]
        self.local_prepare = local_prepare
        self.cloud_allowed = bool(cloud_allowed)
        self.fallbacks_used = 0
        self.last_provider: str | None = None
        self.last_errors: list[str] = []

    def _cloud_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return [{"role": str(m.get("role", "user")), "content": PrivacySanitizer.redact_secrets(str(m.get("content", "")))} for m in messages]

    def _try_local(self, messages, response_format):
        if self.local_provider is None:
            raise ProviderUnavailable("local provider is not configured")
        if self.local_prepare is not None:
            self.local_prepare()
        result = self.local_provider.complete(messages, response_format)
        self.last_provider = "local"
        return result

    def _try_cloud(self, provider, messages, response_format):
        if hasattr(provider, "configured") and not provider.configured:
            raise ProviderUnavailable(f"{getattr(provider, 'name', 'cloud')} is not configured")
        verified = getattr(provider, "zero_cost_verified", None)
        eligible = getattr(provider, "zero_cost_eligible", None)
        if eligible is False or (eligible is None and verified is False and os.environ.get("OFFICE_ALLOW_UNVERIFIED_FREE_TIER", "").strip().lower() not in {"1", "true", "yes", "on"}):
            raise ProviderUnavailable(
                f"{getattr(provider, 'name', 'cloud')} free-tier billing cannot be verified; "
                "set OFFICE_ALLOW_UNVERIFIED_FREE_TIER=1 only after confirming the account cannot incur charges"
            )
        result = provider.complete(self._cloud_messages(messages), response_format)
        self.last_provider = getattr(provider, "name", provider.__class__.__name__)
        return result

    def complete(self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None) -> ModelResponse:
        attempts = []
        if not self.is_review:
            attempts.append(("local", self.local_provider))
        if self.cloud_allowed:
            attempts.extend(("cloud", provider) for provider in self.cloud_providers)
        if self.is_review:
            attempts.append(("local", self.local_provider))
        errors: list[str] = []
        for kind, provider in attempts:
            if provider is None:
                continue
            try:
                return self._try_local(messages, response_format) if kind == "local" else self._try_cloud(provider, messages, response_format)
            except Exception as exc:
                self.fallbacks_used += 1
                errors.append(f"{getattr(provider, 'name', kind)}: {PrivacySanitizer.redact_secrets(str(exc))}")
        self.last_errors = errors
        detail = "; ".join(errors) if errors else "no providers configured"
        raise RuntimeError(f"no model provider completed request ({detail})")

    def status(self) -> dict[str, Any]:
        return {
            "type": "hybrid",
            "review": self.is_review,
            "local_configured": self.local_provider is not None,
            "cloud_allowed": self.cloud_allowed,
            "cloud": [p.status() if hasattr(p, "status") else {"provider": getattr(p, "name", p.__class__.__name__)} for p in self.cloud_providers],
            "last_provider": self.last_provider,
            "fallbacks_used": self.fallbacks_used,
        }
