from pathlib import Path
import json

from engineering_office.models import Verdict
from engineering_office.verification import AcceptanceSnapshot, AcceptanceSpec, Verifier


def write_spec(path: Path, command="python -c \"print('PASS-MARK')\"", required_output="PASS-MARK", required_evidence=None):
    data={"gates":[{"name":"tests","command":command,"expected_exit":0,"required_output":required_output}],"required_evidence":required_evidence or []}
    path.write_text(json.dumps(data))
    return AcceptanceSpec.load(path)


def test_verifier_passes_all_gates(tmp_path: Path):
    acc=tmp_path/"acceptance.json"; spec=write_spec(acc)
    snapshot=AcceptanceSnapshot.capture([acc])
    report=Verifier(tmp_path).verify(spec, snapshot, evidence_refs=[])
    assert report.verdict is Verdict.PASS
    assert report.checks[0]["passed"] is True


def test_verifier_fails_command_gate(tmp_path: Path):
    acc=tmp_path/"acceptance.json"; spec=write_spec(acc, "python -c \"raise SystemExit(2)\"", None)
    snapshot=AcceptanceSnapshot.capture([acc])
    report=Verifier(tmp_path).verify(spec, snapshot, evidence_refs=[])
    assert report.verdict is Verdict.FAIL


def test_acceptance_mutation_after_snapshot_forces_failure(tmp_path: Path):
    acc=tmp_path/"acceptance.json"; spec=write_spec(acc)
    snapshot=AcceptanceSnapshot.capture([acc])
    acc.write_text('{"gates":[]}')
    report=Verifier(tmp_path).verify(spec, snapshot, evidence_refs=[])
    assert report.verdict is Verdict.FAIL
    assert any("changed" in r.lower() for r in report.reasons)


def test_missing_required_evidence_blocks_verification(tmp_path: Path):
    acc=tmp_path/"acceptance.json"; spec=write_spec(acc, required_evidence=["reproduction-log","diff"])
    snapshot=AcceptanceSnapshot.capture([acc])
    report=Verifier(tmp_path).verify(spec, snapshot, evidence_refs=["diff-123"])
    assert report.verdict is Verdict.BLOCKED
    assert "reproduction-log" in " ".join(report.reasons)


def test_required_output_is_checked(tmp_path: Path):
    acc=tmp_path/"acceptance.json"; spec=write_spec(acc, "python -c \"print('wrong')\"", "PASS-MARK")
    snapshot=AcceptanceSnapshot.capture([acc])
    report=Verifier(tmp_path).verify(spec, snapshot, evidence_refs=[])
    assert report.verdict is Verdict.FAIL
