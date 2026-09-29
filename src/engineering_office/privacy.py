from __future__ import annotations

import os

from .evidence import redact_secrets as _redact_secrets


class PrivacySanitizer:
    """Redact credentials before evidence leaves the local machine."""

    _KNOWN_ENV_KEYS = (
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
    )

    @staticmethod
    def redact_secrets(text: str) -> str:
        if not text:
            return text
        out = str(text)
        # Exact environment values are replaced first because provider key formats
        # evolve faster than regexes do.
        for key in PrivacySanitizer._KNOWN_ENV_KEYS:
            value = os.environ.get(key)
            if value:
                out = out.replace(value, f"[REDACTED_{key}]")
        return _redact_secrets(out)


class SanitizedEvidenceBuilder:
    @staticmethod
    def build(task: str, snippets: list[str], failures: list[str], hypothesis: str = "") -> str:
        parts = ["TASK:", task, "", "EVIDENCE:"]
        parts.extend(f"- {item}" for item in snippets)
        if failures:
            parts.extend(["", "TEST FAILURES:"])
            parts.extend(f"- {item}" for item in failures)
        if hypothesis:
            parts.extend(["", "HYPOTHESIS:", hypothesis])
        return PrivacySanitizer.redact_secrets("\n".join(parts) + "\n")
