from __future__ import annotations
import json
from pathlib import Path

from engineering_office.audit_runner import FastAuditRunner
from engineering_office.office import OfficeEngine
from engineering_office.project_index import ProjectIndex
from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, NemotronRuntimeBenchmark
from engineering_office.ui_service import DashboardService


def seed(root: Path, *, gate_command: str = 'python -m unittest discover -s tests -q') -> None:
    (root/'src').mkdir(); (root/'tests').mkdir()
    (root/'src'/'__init__.py').write_text('')
    (root/'src'/'maths.py').write_text('def add(a,b):\n    return a+b\n')
    (root/'tests'/'test_maths.py').write_text(
        'import unittest\nfrom src.maths import add\n\nclass T(unittest.TestCase):\n'
        '    def test_add(self): self.assertEqual(add(2,3),5)\n'
    )
    (root/'acceptance.json').write_text(json.dumps({'gates':[{'name':'gate','command':gate_command,'expected_exit':0}],'required_evidence':[]}))


def test_first_and_second_fast_audit_preserve_source_and_reuse_unchanged_index(tmp_path: Path):
    seed(tmp_path); engine=OfficeEngine(tmp_path); engine.start('audit it')
    source=(tmp_path/'src'/'maths.py').read_bytes()
    first=FastAuditRunner(engine).run('fast-audit','audit it')
    second=FastAuditRunner(engine).run('fast-audit','audit it')
    assert first['status']=='AUDIT_COMPLETE_LIMITED' and second['status']=='AUDIT_COMPLETE_LIMITED'
    assert (tmp_path/'src'/'maths.py').read_bytes()==source
    assert first['index']['changed_count'] >= 1
    assert second['index']['changed_count'] == 0
    assert second['index']['unchanged_count'] >= 1
    assert Path(second['report_dir'],'REPORT.md').is_file()


def test_blocked_audit_still_writes_report(tmp_path: Path, monkeypatch):
    seed(tmp_path); engine=OfficeEngine(tmp_path); engine.start('audit it')
    monkeypatch.setattr(ProjectIndex,'update',lambda self: (_ for _ in ()).throw(RuntimeError('index unavailable')))
    result=FastAuditRunner(engine).run('check-report','audit it')
    assert result['status']=='BLOCKED'
    report=Path(result['report_dir'],'REPORT.md')
    assert report.is_file()
    assert 'index unavailable' in report.read_text()


def test_run_timing_report_index_and_needs_user_are_visible_to_dashboard(tmp_path: Path):
    seed(tmp_path); engine=OfficeEngine(tmp_path); engine.start('audit it')
    FastAuditRunner(engine).run('check-report','audit it')
    service=DashboardService(tmp_path,floor_registry_path=tmp_path/'floors.json')
    assert service.current_run()['run_id'].startswith('RUN-')
    timing=service.run_timing(); assert timing['total_elapsed_seconds'] >= 0 and 'eta' in timing
    assert service.run_report()['available'] is True
    assert service.index_status()['file_count'] >= 1
    assert service.needs_user()['count'] == 0


def test_unsupported_nemotron_challenger_keeps_llama_baseline(tmp_path: Path):
    registry=RuntimeBenchmarkRegistry(tmp_path)
    decision=NemotronRuntimeBenchmark(registry).evaluate('fp',llama={'median_latency_seconds':10,'correctness':1,'stable':True,'ram_ok':True},challenger_capability={'supported':False},challenger=None)
    assert decision.selected_strategy == 'llama.cpp'
    assert decision.status == 'SKIPPED_UNSUPPORTED'
    assert decision.reason == 'unsupported'


def test_release_contains_friendly_fast_audit_assets_and_changelog_entry():
    root=Path(__file__).resolve().parents[1]
    html=(root/'src/engineering_office/ui/index.html').read_text()
    app=(root/'src/engineering_office/ui/app.js').read_text()
    for token in ['run-overview','run-total-time','run-stage-time','run-eta','needs-you-card','run-mode-select']:
        assert token in html
    assert 'friendlyEvent' in app and 'ACTIVITY' in app
    assert (root/'docs/assets/fast-audit-friendly-control-room.png').is_file()
    change=(root/'CHANGELOG.md').read_text()
    assert 'Fast Audit' in change and 'User-Friendly Control Room' in change
