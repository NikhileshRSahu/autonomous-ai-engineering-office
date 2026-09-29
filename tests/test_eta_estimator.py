from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path


def make_record(run_id, seconds, *, status="AUDIT_COMPLETE", mode="fast-audit", current_stage="REPORT"):
    from engineering_office.run_records import RunRecord, RunStageState
    start=datetime(2026,9,28,4,0,tzinfo=timezone.utc)
    end=start+timedelta(seconds=seconds)
    return RunRecord(run_id,"P",mode,"audit",status,start.isoformat(),end.isoformat(),current_stage,end.isoformat(),[RunStageState("IMPORT","PASS",start.isoformat(),(start+timedelta(seconds=10)).isoformat()),RunStageState("REPORT","PASS",(start+timedelta(seconds=10)).isoformat(),end.isoformat())])


def active_record(elapsed, *, mode="fast-audit"):
    from engineering_office.run_records import RunRecord, RunStageState
    now=datetime.now(timezone.utc); start=now-timedelta(seconds=elapsed)
    return RunRecord("ACTIVE","P",mode,"audit","RUNNING",start.isoformat(),None,"ANALYZE",start.isoformat(),[RunStageState("ANALYZE","RUNNING",start.isoformat(),None)])


def test_learning_until_three_comparable_completed_runs(tmp_path: Path):
    from engineering_office.eta import EtaEstimator
    est=EtaEstimator(tmp_path)
    features={"project_type":"robotics","model_state":"warm"}
    est.record(make_record("r1",100),features); est.record(make_record("r2",120),features)
    out=est.estimate(active_record(20),features)
    assert out.state == "LEARNING" and out.sample_count == 2


def test_deterministic_p50_p80_remaining_range(tmp_path: Path):
    from engineering_office.eta import EtaEstimator
    est=EtaEstimator(tmp_path); f={"project_type":"robotics","model_state":"warm"}
    for i,d in enumerate([100,120,140,160,180]): est.record(make_record(f"r{i}",d),f)
    out=est.estimate(active_record(50),f)
    assert out.state == "READY"
    assert out.sample_count == 5
    assert out.lower_seconds == 90  # p50 total=140 minus elapsed 50
    assert out.upper_seconds == 130 # p80 total=180 minus elapsed 50


def test_blocked_run_excluded_from_completion_population(tmp_path: Path):
    from engineering_office.eta import EtaEstimator
    est=EtaEstimator(tmp_path); f={"project_type":"robotics","model_state":"warm"}
    for i,d in enumerate([100,110,120]): est.record(make_record(f"r{i}",d),f)
    est.record(make_record("blocked",1000,status="BLOCKED"),f)
    out=est.estimate(active_record(0),f)
    assert out.sample_count == 3
    assert out.upper_seconds < 200


def test_warm_and_cold_models_do_not_mix(tmp_path: Path):
    from engineering_office.eta import EtaEstimator
    est=EtaEstimator(tmp_path)
    for i in range(3): est.record(make_record(f"w{i}",100+i),{"project_type":"robotics","model_state":"warm"})
    for i in range(3): est.record(make_record(f"c{i}",600+i),{"project_type":"robotics","model_state":"cold"})
    warm=est.estimate(active_record(0),{"project_type":"robotics","model_state":"warm"})
    cold=est.estimate(active_record(0),{"project_type":"robotics","model_state":"cold"})
    assert warm.upper_seconds < 200
    assert cold.lower_seconds > 500


def test_finished_record_eta_is_zero(tmp_path: Path):
    from engineering_office.eta import EtaEstimator
    est=EtaEstimator(tmp_path); f={"project_type":"robotics","model_state":"warm"}
    for i in range(3): est.record(make_record(f"r{i}",100+i),f)
    out=est.estimate(make_record("done",90),f)
    assert out.lower_seconds == 0 and out.upper_seconds == 0
