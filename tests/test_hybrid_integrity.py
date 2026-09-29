from __future__ import annotations

import json
from pathlib import Path

from engineering_office.reporting import RunReportBuilder
from engineering_office.run_records import RunRecord


def _record(root: Path, status: str = "AUDIT_COMPLETE_LIMITED") -> RunRecord:
    return RunRecord(
        run_id="RUN-test",
        project_id="P-test",
        mode="fast-audit",
        objective="tell me what this project does",
        status=status,
        started_at_utc="2026-09-28T10:00:00+00:00",
        finished_at_utc="2026-09-28T10:01:00+00:00",
        current_stage="REPORT",
        stage_started_at_utc="2026-09-28T10:00:30+00:00",
        stages=[],
    )


def test_report_never_fabricates_models_or_cloud_providers(tmp_path: Path):
    path = RunReportBuilder(tmp_path).build(
        _record(tmp_path),
        findings=[{"severity":"info","message":"Technologies: Python, ROS 2"}],
        tests=[],
        risks=[],
        model_metrics={},
        skipped={"qwen_analysis":"No routed model configured", "nemotron_review":"No reviewer configured"},
    )
    text = (path / "REPORT.md").read_text()
    assert "Qwen 3B" not in text
    assert "llama-3.1-8b-instruct:free" not in text
    assert "gemini-1.5-flash" not in text
    assert "qwen_analysis: No routed model configured" in text
    assert "nemotron_review: No reviewer configured" in text


def test_hybrid_ui_does_not_hardcode_provider_availability():
    root = Path(__file__).resolve().parents[1]
    html = (root / "src/engineering_office/ui/index.html").read_text()
    js = (root / "src/engineering_office/ui/app.js").read_text()
    assert "OpenRouter <span" not in html
    assert "Qwen 3B <span" not in html
    assert "const hasCloud = true" not in js


def test_run_report_exposes_rendered_summary_path(tmp_path: Path):
    from engineering_office.ui_service import DashboardService
    from engineering_office.run_records import RunRecordStore

    office = tmp_path / ".office"
    office.mkdir()
    rec = _record(tmp_path, "AUDIT_COMPLETE")
    RunRecordStore(tmp_path).save(rec)
    report_dir = office / "reports" / rec.run_id
    report_dir.mkdir(parents=True)
    (report_dir / "REPORT.md").write_text("# report")
    (report_dir / "SUMMARY.html").write_text("<h1>report</h1>")
    service = DashboardService(tmp_path)
    info = service.run_report()
    assert info["available"] is True
    assert info["summary_path"] == f"reports/{rec.run_id}/SUMMARY.html"


def test_summary_html_is_user_facing_and_escapes_findings(tmp_path: Path):
    path = RunReportBuilder(tmp_path).build(
        _record(tmp_path),
        findings=[
            {"severity":"info","message":"Technologies: Python, ROS 2"},
            {"severity":"warning","message":"<script>alert(1)</script> runtime not checked"},
        ],
        tests=[{"name":"unit","status":"PASS"}],
        risks=[{"risk":"simulation not executed"}],
        model_metrics={},
        skipped={"gazebo":"not requested"},
    )
    html=(path/"SUMMARY.html").read_text()
    assert "WHAT THIS PROJECT DOES" in html
    assert "Python, ROS 2" in html
    assert "Skipped / unavailable checks" in html
    assert "gazebo" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_provider_status_is_secret_safe(tmp_path: Path, monkeypatch):
    from engineering_office.ui_service import DashboardService
    monkeypatch.setenv("OPENROUTER_API_KEY", "super-secret-key")
    service=DashboardService(tmp_path)
    status=service.provider_status()
    assert status["cloud"]["openrouter"]["configured"] is True
    assert "super-secret-key" not in json.dumps(status)


def test_provider_status_does_not_call_cloud_only_router_local(tmp_path: Path, monkeypatch):
    from engineering_office.office import OfficeEngine
    from engineering_office.ui_service import DashboardService
    OfficeEngine(tmp_path).start("inspect")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    service=DashboardService(tmp_path)
    assert service.engine.model_router is not None
    status=service.provider_status()
    assert status["local"]["configured"] is False
    assert status["cloud"]["openrouter"]["configured"] is True


def test_header_does_not_claim_unverified_zero_cost():
    root = Path(__file__).resolve().parents[1]
    html=(root/"src/engineering_office/ui/index.html").read_text()
    assert "HYBRID ZERO COST" not in html


def test_cloud_only_router_is_not_reported_as_local_model(tmp_path: Path, monkeypatch):
    from engineering_office.cli import _router_from_config
    from engineering_office.ui_service import DashboardService

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    root = tmp_path
    office = root / ".office"
    office.mkdir()
    (office / "project.json").write_text(json.dumps({"project_id":"P-test","root":str(root),"objective":"audit","project_type":"software","technologies":[],"broken_components":[],"risk_areas":[],"unknowns":[],"constraints":[],"dependencies":[],"entry_points":[],"test_commands":[]}))
    service = DashboardService(root)
    # Inject a cloud-only router so the status projection cannot infer local
    # readiness merely from the existence of a ModelRouter.
    service.engine.model_router = _router_from_config(None, project_root=root)
    status = service.provider_status()
    assert status["local"]["configured"] is False
    assert status["cloud"]["openrouter"]["configured"] is True


def test_report_uses_actual_model_provenance_not_role_names(tmp_path: Path):
    path = RunReportBuilder(tmp_path).build(
        _record(tmp_path, "AUDIT_COMPLETE"),
        findings=[{"severity":"info","message":"Technologies: Python"}],
        tests=[], risks=[], skipped={},
        model_metrics={
            "analysis": {"provider":"OpenRouter", "model":"some/free-model", "calls":1},
            "review": {"provider":"Gemini", "model":"gemini-example", "calls":1},
        },
    )
    text = (path / "REPORT.md").read_text()
    assert "OpenRouter · some/free-model" in text
    assert "Gemini · gemini-example" in text
    assert "fully analyzed by Qwen and reviewed by Nemotron" not in text


def test_audit_response_metrics_preserve_actual_provider_and_model():
    from engineering_office.audit_runner import FastAuditRunner
    from engineering_office.models_runtime import ModelResponse

    response = ModelResponse(
        '{"findings": [], "risks": []}',
        usage={"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
        raw={"provider": "OpenRouter", "model": "vendor/free-model", "response": {}},
    )
    metrics = FastAuditRunner._response_metrics(response)
    assert metrics["provider"] == "OpenRouter"
    assert metrics["model"] == "vendor/free-model"
    assert metrics["prompt_tokens"] == 12
    assert metrics["completion_tokens"] == 7
    assert metrics["total_tokens"] == 19


def test_limited_report_does_not_assume_missing_models_are_local(tmp_path: Path):
    path = RunReportBuilder(tmp_path).build(
        _record(tmp_path),
        findings=[{"severity":"info","message":"Technologies: Python"}],
        tests=[], risks=[], model_metrics={},
        skipped={"qwen_analysis":"all configured providers unavailable"},
    )
    text = (path / "REPORT.md").read_text()
    assert "required local AI models were unavailable" not in text
    assert "Qwen/Nemotron" not in text
    assert "required AI analysis" in text


def test_fast_audit_records_actual_provider_and_model_provenance(tmp_path: Path):
    from engineering_office.audit_runner import FastAuditRunner
    from engineering_office.models_runtime import ModelRouter, ModelResponse
    from engineering_office.office import OfficeEngine
    from engineering_office.models import Complexity

    class Provider:
        def __init__(self, provider, model, payload):
            self.provider=provider; self.model=model; self.payload=payload
        def complete(self, messages, response_format=None):
            return ModelResponse(
                json.dumps(self.payload),
                usage={"prompt_tokens":10,"completion_tokens":5,"total_tokens":15},
                raw={"provider":self.provider,"model":self.model},
            )

    (tmp_path/"src").mkdir()
    (tmp_path/"src"/"app.py").write_text("print('hello')\n")
    (tmp_path/"acceptance.json").write_text(json.dumps({"gates":[{"name":"smoke","command":"python -c \"print(1)\"","expected_exit":0}],"required_evidence":[]}))
    analysis=Provider("OpenRouter","free-coder",{"findings":[],"risks":[]})
    review=Provider("Gemini","review-model",{"findings":[],"risks":[]})
    router=ModelRouter({Complexity.LOW:analysis, Complexity.HIGH:review})
    engine=OfficeEngine(tmp_path, model_router=router)
    engine.start("tell me what this project does")
    result=FastAuditRunner(engine).run("fast-audit","tell me what this project does")
    assert result["model_metrics"]["analysis"]["provider"] == "OpenRouter"
    assert result["model_metrics"]["analysis"]["model"] == "free-coder"
    assert result["model_metrics"]["review"]["provider"] == "Gemini"
    assert result["model_metrics"]["review"]["model"] == "review-model"


def test_provider_status_distinguishes_configured_from_zero_cost_eligible(tmp_path: Path, monkeypatch):
    from engineering_office.ui_service import DashboardService
    monkeypatch.setenv("GROQ_API_KEY", "key")
    monkeypatch.delenv("OFFICE_ALLOW_UNVERIFIED_FREE_TIER", raising=False)
    service=DashboardService(tmp_path)
    status=service.provider_status()
    assert status["cloud"]["groq"]["configured"] is True
    assert status["cloud"]["groq"]["zero_cost_eligible"] is False
    assert status["zero_cost_only"] is True


def test_control_room_uses_zero_cost_eligibility_not_just_key_presence():
    root=Path(__file__).resolve().parents[1]
    js=(root/"src/engineering_office/ui/app.js").read_text()
    assert "zero_cost_eligible" in js
    assert "needs zero-cost confirmation" in js
