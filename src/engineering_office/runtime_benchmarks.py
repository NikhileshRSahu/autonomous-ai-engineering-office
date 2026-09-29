from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import hashlib
import json


@dataclass(slots=True)
class BenchmarkDecision:
    kind: str
    fingerprint: str
    status: str
    selected: bool
    selected_strategy: str
    baseline: dict[str, Any]
    candidate: dict[str, Any] | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeBenchmarkRegistry:
    def __init__(self, project_root: str | Path):
        root = Path(project_root).resolve()
        self.path = root / ".office" / "benchmarks" / "runtime-strategies.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def fingerprint(*parts: dict[str, Any]) -> str:
        payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(payload).hexdigest()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text())
            return raw if isinstance(raw, list) else []
        except Exception:
            return []

    def record(self, kind: str, result: dict[str, Any]) -> None:
        rows = self._load()
        row = {"kind": kind, **result}
        rows = [r for r in rows if not (r.get("kind") == kind and r.get("fingerprint") == row.get("fingerprint"))]
        rows.append(row)
        self.path.write_text(json.dumps(rows, indent=2, sort_keys=True, default=str))

    def selected(self, kind: str, fingerprint: str | None = None) -> dict[str, Any] | None:
        rows = [r for r in self._load() if r.get("kind") == kind and r.get("selected")]
        if fingerprint is not None:
            rows = [r for r in rows if r.get("fingerprint") == fingerprint]
        return rows[-1] if rows else None


class _BaseComparison:
    kind = "runtime"
    default_strategy = "baseline"
    candidate_strategy = "candidate"

    def __init__(self, registry: RuntimeBenchmarkRegistry):
        self.registry = registry

    @staticmethod
    def _run(adapter) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        capability = adapter.capability()
        if not capability.get("supported"):
            return None, capability
        return adapter.run(), capability

    def evaluate(self, fingerprint: str, *, baseline, candidate) -> BenchmarkDecision:
        base, base_cap = self._run(baseline)
        cand, cand_cap = self._run(candidate)
        if base is None:
            decision = BenchmarkDecision(self.kind, fingerprint, "BENCHMARK_FAILED", False, self.default_strategy, {}, None, "baseline_unavailable")
        elif cand is None:
            decision = BenchmarkDecision(self.kind, fingerprint, "SKIPPED_UNSUPPORTED", False, self.default_strategy, base, None, cand_cap.get("reason") or "unsupported")
        elif not cand.get("correct", False):
            decision = BenchmarkDecision(self.kind, fingerprint, "SUPPORTED_AND_BENCHMARKED", False, self.default_strategy, base, cand, "correctness_gate_failed")
        elif not cand.get("ram_ok", True):
            decision = BenchmarkDecision(self.kind, fingerprint, "SUPPORTED_AND_BENCHMARKED", False, self.default_strategy, base, cand, "memory_guard_failed")
        elif not cand.get("stable", True):
            decision = BenchmarkDecision(self.kind, fingerprint, "SUPPORTED_AND_BENCHMARKED", False, self.default_strategy, base, cand, "stability_gate_failed")
        elif float(cand.get("latency_seconds", 1e99)) >= float(base.get("latency_seconds", 1e99)):
            decision = BenchmarkDecision(self.kind, fingerprint, "SUPPORTED_AND_BENCHMARKED", False, self.default_strategy, base, cand, "candidate_not_faster")
        else:
            decision = BenchmarkDecision(self.kind, fingerprint, "SUPPORTED_AND_BENCHMARKED", True, self.candidate_strategy, base, cand, None)
        self.registry.record(self.kind, decision.to_dict())
        return decision


class VllmSleepBenchmark(_BaseComparison):
    kind = "vllm_sleep"
    default_strategy = "llama_cold"
    candidate_strategy = "vllm_sleep"


class LlamaWarmLoadBenchmark(_BaseComparison):
    kind = "llama_warm_load"
    default_strategy = "cold"
    candidate_strategy = "warm"

    def evaluate(self, fingerprint: str, *, cold, warm) -> BenchmarkDecision:
        return super().evaluate(fingerprint, baseline=cold, candidate=warm)


def _median(values: list[float]) -> float:
    values = sorted(float(v) for v in values)
    if not values:
        return float("inf")
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid-1] + values[mid]) / 2.0


class QwenSpeculativeBenchmark:
    kind = "qwen_speculative"

    def __init__(self, registry: RuntimeBenchmarkRegistry, min_improvement: float = 0.15):
        self.registry = registry
        self.min_improvement = float(min_improvement)

    def evaluate(self, fingerprint: str, *, baseline: dict[str, Any], candidates: dict[str, dict[str, Any]]) -> BenchmarkDecision:
        base_latency = _median(list(baseline.get("latencies_seconds", [])))
        best_name = "baseline"
        best_latency = base_latency
        best_result = None
        for name, result in candidates.items():
            if not result.get("correct", False) or not result.get("stable", True) or not result.get("ram_ok", True):
                continue
            latency = _median(list(result.get("latencies_seconds", [])))
            if latency <= base_latency * (1.0 - self.min_improvement) and latency < best_latency:
                best_name, best_latency, best_result = name, latency, result
        selected = best_name != "baseline"
        reason = None if selected else "no_candidate_met_speed_and_correctness_gate"
        decision = BenchmarkDecision(self.kind, fingerprint, "SUPPORTED_AND_BENCHMARKED", selected, best_name, baseline, best_result, reason)
        self.registry.record(self.kind, decision.to_dict())
        return decision


class NemotronRuntimeBenchmark:
    kind = "nemotron_runtime"

    def __init__(self, registry: RuntimeBenchmarkRegistry):
        self.registry = registry

    def evaluate(self, fingerprint: str, *, llama: dict[str, Any], challenger_capability: dict[str, Any], challenger: dict[str, Any] | None) -> BenchmarkDecision:
        if not challenger_capability.get("supported"):
            decision = BenchmarkDecision(self.kind, fingerprint, "SKIPPED_UNSUPPORTED", False, "llama.cpp", llama, None, challenger_capability.get("reason") or "unsupported")
        else:
            llama_latency = _median(list(llama.get("latencies_seconds", [])))
            challenger = challenger or {}
            challenger_latency = _median(list(challenger.get("latencies_seconds", [])))
            selected = bool(challenger.get("correct", False) and challenger.get("stable", True) and challenger.get("ram_ok", True) and challenger_latency < llama_latency)
            reason = None if selected else ("correctness_gate_failed" if not challenger.get("correct", False) else "candidate_not_faster")
            decision = BenchmarkDecision(self.kind, fingerprint, "SUPPORTED_AND_BENCHMARKED", selected, "tensorrt-nvfp4" if selected else "llama.cpp", llama, challenger, reason)
        self.registry.record(self.kind, decision.to_dict())
        return decision
