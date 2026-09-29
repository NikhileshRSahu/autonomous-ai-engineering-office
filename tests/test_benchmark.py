from pathlib import Path
import json

from engineering_office.benchmark import BenchmarkCase, BenchmarkResult, BenchmarkSuite


def test_summary_calculates_verified_completion_and_false_pass_rate():
    suite=BenchmarkSuite([
        BenchmarkResult("c1", understood=True, specialist_correct=True, root_cause_correct=True, verified_complete=True, false_pass=False, regression=False, human_interventions=0, iterations=1, elapsed_seconds=10, tokens=100),
        BenchmarkResult("c2", understood=True, specialist_correct=False, root_cause_correct=False, verified_complete=False, false_pass=False, regression=False, human_interventions=1, iterations=3, elapsed_seconds=30, tokens=300),
        BenchmarkResult("c3", understood=True, specialist_correct=True, root_cause_correct=False, verified_complete=False, false_pass=True, regression=True, human_interventions=0, iterations=2, elapsed_seconds=20, tokens=200),
    ])
    s=suite.summary()
    assert s["cases"] == 3
    assert s["verified_autonomous_task_completion_rate"] == 1/3
    assert s["false_pass_rate"] == 1/3
    assert s["regression_rate"] == 1/3
    assert s["average_iterations"] == 2.0


def test_empty_suite_has_zero_rates():
    s=BenchmarkSuite([]).summary()
    assert s["cases"] == 0
    assert s["verified_autonomous_task_completion_rate"] == 0.0
    assert s["false_pass_rate"] == 0.0


def test_suite_loads_results_json(tmp_path: Path):
    p=tmp_path/"results.json"
    p.write_text(json.dumps([{"case_id":"x","understood":True,"specialist_correct":True,"root_cause_correct":True,"verified_complete":True,"false_pass":False,"regression":False,"human_interventions":0,"iterations":1,"elapsed_seconds":1.2,"tokens":4}]))
    suite=BenchmarkSuite.from_json(p)
    assert suite.summary()["cases"] == 1
