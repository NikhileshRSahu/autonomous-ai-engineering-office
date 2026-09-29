from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import math

from .run_records import RunRecord


@dataclass(slots=True)
class RunTimingSample:
    run_id: str
    mode: str
    status: str
    total_seconds: float
    features: dict[str, Any]
    stage_seconds: dict[str, float]


@dataclass(slots=True)
class EtaEstimate:
    state: str
    lower_seconds: float | None
    upper_seconds: float | None
    sample_count: int
    label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EtaEstimator:
    COMPARABLE_KEYS = ("project_type", "model_state", "simulation_level", "runtime_strategy")

    def __init__(self, project_root: str | Path):
        root = Path(project_root).resolve()
        self.path = root / ".office" / "history" / "run_timings.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _dt(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    @classmethod
    def _duration(cls, record: RunRecord) -> float:
        start = cls._dt(record.started_at_utc)
        end = cls._dt(record.finished_at_utc)
        return max(0.0, (end - start).total_seconds()) if start and end else 0.0

    @classmethod
    def _stage_durations(cls, record: RunRecord) -> dict[str, float]:
        result: dict[str, float] = {}
        for stage in record.stages:
            start, end = cls._dt(stage.started_at_utc), cls._dt(stage.finished_at_utc)
            if start and end:
                result[stage.name] = max(0.0, (end - start).total_seconds())
        return result

    def record(self, record: RunRecord, features: dict[str, Any]) -> None:
        if record.finished_at_utc is None:
            return
        sample = RunTimingSample(record.run_id, record.mode, record.status, self._duration(record), dict(features), self._stage_durations(record))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(sample), sort_keys=True, default=str) + "\n")

    def _samples(self) -> list[RunTimingSample]:
        if not self.path.is_file():
            return []
        rows: list[RunTimingSample] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                raw = json.loads(line)
                rows.append(RunTimingSample(**raw))
            except Exception:
                continue
        return rows

    @classmethod
    def _comparable(cls, sample: RunTimingSample, record: RunRecord, features: dict[str, Any]) -> bool:
        if sample.mode != record.mode:
            return False
        for key in cls.COMPARABLE_KEYS:
            if key in features or key in sample.features:
                if sample.features.get(key) != features.get(key):
                    return False
        return True

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        values = sorted(values)
        if not values:
            return 0.0
        idx = min(len(values)-1, max(0, int(math.ceil(q * (len(values)-1)))))
        return float(values[idx])

    def estimate(self, active_record: RunRecord, features: dict[str, Any]) -> EtaEstimate:
        if active_record.finished_at_utc is not None:
            return EtaEstimate("COMPLETE", 0.0, 0.0, 0, "Complete")
        completed = [s for s in self._samples() if s.status in {"PASS", "AUDIT_COMPLETE"} and self._comparable(s, active_record, features)]
        if len(completed) < 3:
            return EtaEstimate("LEARNING", None, None, len(completed), "Learning from this run…")
        start = self._dt(active_record.started_at_utc)
        now = datetime.now(timezone.utc)
        elapsed = max(0.0, (now - start).total_seconds()) if start else 0.0
        totals = [s.total_seconds for s in completed]
        low = max(0.0, self._percentile(totals, 0.50) - elapsed)
        high = max(low, self._percentile(totals, 0.80) - elapsed)
        return EtaEstimate("READY", round(low, 3), round(high, 3), len(completed), f"~{int(low)}–{int(high)}s remaining")
