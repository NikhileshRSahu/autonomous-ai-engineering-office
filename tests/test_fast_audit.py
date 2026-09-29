from pathlib import Path


def test_fast_audit_plan_is_cheap_first_and_batches_models(tmp_path: Path):
    from engineering_office.fast_audit import FastAuditPlanner
    from engineering_office.project_index import IndexUpdate
    plan = FastAuditPlanner().plan(IndexUpdate(2, changed=["src/a.py"], unchanged=["README.md"], removed=[], excluded=[]), simulation_requested=False)
    assert plan.stages == ["IMPORT", "INDEX", "ANALYZE", "TEST", "REVIEW", "REPORT"]
    assert plan.model_phase_budget == {"qwen": 1, "nemotron": 1, "qwen_followup": 1}
    assert plan.actions.index("static_analysis") < plan.actions.index("targeted_tests")
    assert "full_simulation" not in plan.actions
    assert plan.skipped["full_simulation"]


def test_fast_audit_simulation_can_be_requested():
    from engineering_office.fast_audit import FastAuditPlanner
    from engineering_office.project_index import IndexUpdate
    plan = FastAuditPlanner().plan(IndexUpdate(1), simulation_requested=True)
    assert "full_simulation" in plan.actions
