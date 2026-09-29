from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(slots=True)
class BenchmarkCase:
    case_id: str
    category: str
    objective: str
    expected_root_cause: str | None = None


@dataclass(slots=True)
class BenchmarkResult:
    case_id: str
    understood: bool
    specialist_correct: bool
    root_cause_correct: bool
    verified_complete: bool
    false_pass: bool
    regression: bool
    human_interventions: int
    iterations: int
    elapsed_seconds: float
    tokens: int = 0


class BenchmarkSuite:
    def __init__(self, results: list[BenchmarkResult]):
        self.results=results

    @classmethod
    def from_json(cls, path: str | Path | None) -> "BenchmarkSuite":
        if path is None:
            return cls([])
        raw=json.loads(Path(path).read_text())
        if not isinstance(raw,list): raise ValueError("benchmark input must be a JSON list")
        return cls([BenchmarkResult(**item) for item in raw])

    def summary(self) -> dict:
        n=len(self.results)
        if n == 0:
            return {
                "cases":0,"project_understanding_rate":0.0,"specialist_selection_accuracy":0.0,
                "root_cause_accuracy":0.0,"verified_autonomous_task_completion_rate":0.0,
                "false_pass_rate":0.0,"regression_rate":0.0,"average_human_interventions":0.0,
                "average_iterations":0.0,"average_elapsed_seconds":0.0,"total_tokens":0,
            }
        rate=lambda attr: sum(bool(getattr(r,attr)) for r in self.results)/n
        return {
            "cases":n,
            "project_understanding_rate":rate("understood"),
            "specialist_selection_accuracy":rate("specialist_correct"),
            "root_cause_accuracy":rate("root_cause_correct"),
            "verified_autonomous_task_completion_rate":rate("verified_complete"),
            "false_pass_rate":rate("false_pass"),
            "regression_rate":rate("regression"),
            "average_human_interventions":sum(r.human_interventions for r in self.results)/n,
            "average_iterations":sum(r.iterations for r in self.results)/n,
            "average_elapsed_seconds":sum(r.elapsed_seconds for r in self.results)/n,
            "total_tokens":sum(r.tokens for r in self.results),
        }


@dataclass(slots=True)
class BenchmarkCatalog:
    cases: list[BenchmarkCase]

    @classmethod
    def load(cls, path: str | Path) -> "BenchmarkCatalog":
        raw=json.loads(Path(path).read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
            raise ValueError("benchmark catalog must contain a 'cases' list")
        cases=[BenchmarkCase(**item) for item in raw["cases"]]
        ids=[c.case_id for c in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case IDs must be unique")
        return cls(cases)
