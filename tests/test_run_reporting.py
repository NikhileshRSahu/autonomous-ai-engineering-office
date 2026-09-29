from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json

import pytest


def record(root: Path, status="AUDIT_COMPLETE"):
    from engineering_office.run_records import RunCoordinator
    rc=RunCoordinator(root,project_id="P-1")
    r=rc.start("fast-audit","check project",["IMPORT","INDEX","REPORT"])
    rc.transition("IMPORT","PASS"); rc.transition("INDEX","PASS"); rc.transition("REPORT","RUNNING")
    return rc.finish(status,{"note":"done"})


def test_report_builder_writes_complete_contract_without_implying_pass(tmp_path: Path):
    from engineering_office.reporting import RunReportBuilder
    r=record(tmp_path,"AUDIT_COMPLETE")
    path=RunReportBuilder(tmp_path).build(r,findings=[{"severity":"warning","message":"runtime not checked"}],tests=[{"name":"unit","status":"PASS"}],risks=[{"risk":"simulation not executed"}],model_metrics={"qwen":{"seconds":12}},skipped={"gazebo":"not requested"})
    expected={"REPORT.md","SUMMARY.html","run-metadata.json","timeline.jsonl","findings.json","test-results.json","risks.json","model-performance.json","evidence"}
    assert expected <= {p.name for p in path.iterdir()}
    text=(path/"REPORT.md").read_text()
    assert "AUDIT_COMPLETE" in text
    assert "does not mean project acceptance PASS" in text
    assert "gazebo" in text


def test_blocked_and_partial_runs_still_get_reports(tmp_path: Path):
    from engineering_office.reporting import RunReportBuilder
    for status in ["BLOCKED","PARTIAL","FAIL"]:
        root=tmp_path/status; root.mkdir()
        out=RunReportBuilder(root).build(record(root,status),findings=[],tests=[],risks=[],model_metrics={},skipped={"runtime":"unavailable"})
        assert (out/"REPORT.md").is_file()
        assert json.loads((out/"run-metadata.json").read_text())["status"] == status


def test_office_file_allows_reports_but_denies_traversal(tmp_path: Path):
    from engineering_office.ui_service import DashboardService
    (tmp_path/"README.md").write_text("x")
    report=tmp_path/".office"/"reports"/"R1"; report.mkdir(parents=True); (report/"REPORT.md").write_text("ok")
    service=DashboardService(tmp_path,floor_registry_path=tmp_path/"floors.json")
    data,ctype=service.office_file("reports/R1/REPORT.md")
    assert data == b"ok" and "markdown" in ctype
    with pytest.raises(ValueError): service.office_file("reports/../../README.md")
