from __future__ import annotations
import json
from pathlib import Path

from engineering_office.cli import build_parser, main
from engineering_office.config import OfficeConfig


def seed_project(root: Path) -> None:
    (root / 'src').mkdir()
    (root / 'tests').mkdir()
    (root / 'src' / '__init__.py').write_text('')
    (root / 'src' / 'calc.py').write_text('def add(a, b):\n    return a + b\n')
    (root / 'tests' / 'test_calc.py').write_text(
        'import unittest\nfrom src.calc import add\n\n'
        'class T(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2,3),5)\n'
    "\nif __name__ == '__main__': unittest.main()\n"
    )
    (root / 'acceptance.json').write_text(json.dumps({
        'gates':[{'name':'unittest','command':'python -m unittest discover -s tests -q','expected_exit':0}],
        'required_evidence':[]
    }))


def test_parser_exposes_run_modes_report_and_index_commands():
    parser = build_parser()
    args = parser.parse_args(['run', '.', '--mode', 'fast-audit', '--objective', 'audit it'])
    assert args.mode == 'fast-audit'
    assert args.objective == 'audit it'
    assert parser.parse_args(['report', '.', '--run-id', 'RUN-X']).command == 'report'
    idx = parser.parse_args(['index', 'rebuild', '.'])
    assert idx.index_action == 'rebuild'


def test_backward_compatible_config_gets_safe_audit_defaults(tmp_path: Path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'model_profiles':{}, 'routing':{}}))
    cfg = OfficeConfig.load(path)
    assert cfg.default_run_mode == 'complete'
    assert cfg.fast_audit_max_context_files == 30
    assert cfg.fast_audit_max_context_chars == 200_000


def test_check_report_is_read_only_and_writes_permanent_report(tmp_path: Path, capsys):
    seed_project(tmp_path)
    assert main(['start', str(tmp_path), '--objective', 'understand project']) == 0
    capsys.readouterr()
    before = (tmp_path / 'src' / 'calc.py').read_bytes()
    rc = main(['run', str(tmp_path), '--mode', 'check-report', '--objective', 'check this project and give a report'])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out['status'] == 'AUDIT_COMPLETE_LIMITED'
    assert out['mode'] == 'check-report'
    assert Path(out['report_dir']).joinpath('REPORT.md').is_file()
    assert (tmp_path / 'src' / 'calc.py').read_bytes() == before
    assert out['verification']['verdict'] == 'PASS'


def test_index_status_rebuild_and_report_lookup(tmp_path: Path, capsys):
    seed_project(tmp_path)
    assert main(['start', str(tmp_path), '--objective', 'audit']) == 0
    capsys.readouterr()
    assert main(['index', 'rebuild', str(tmp_path)]) == 0
    rebuilt = json.loads(capsys.readouterr().out)
    assert rebuilt['file_count'] >= 3
    assert main(['index', 'status', str(tmp_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status['generation'] >= 1
    assert main(['run', str(tmp_path), '--mode', 'check-report']) == 0
    capsys.readouterr()
    assert main(['report', str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['available'] is True
    assert Path(report['directory']).is_dir()


def test_benchmark_subcommands_remain_measurement_gated():
    parser = build_parser()
    assert parser.parse_args(['benchmark','residency','.']).benchmark_kind == 'residency'
    speculative = parser.parse_args(['benchmark','speculative','qwen','.'])
    assert speculative.benchmark_kind == 'speculative'
    assert speculative.benchmark_target == 'qwen'
    assert parser.parse_args(['benchmark','nemotron-runtime','.']).benchmark_kind == 'nemotron-runtime'
