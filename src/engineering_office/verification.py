from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from .models import VerificationReport, Verdict
from .security import ApprovalPolicy, PermissionSet, SecurityError
from .tools import ShellTool


@dataclass(slots=True)
class AcceptanceGate:
    name: str
    command: str
    expected_exit: int = 0
    required_output: str | None = None
    timeout: int = 300


@dataclass(slots=True)
class AcceptanceSpec:
    source: Path
    gates: list[AcceptanceGate]
    required_evidence: list[str]

    @classmethod
    def load(cls, path: str | Path) -> "AcceptanceSpec":
        path = Path(path).resolve()
        raw = json.loads(path.read_text())
        gates=[]
        for item in raw.get("gates", []):
            gates.append(AcceptanceGate(
                name=str(item["name"]), command=str(item["command"]),
                expected_exit=int(item.get("expected_exit", 0)),
                required_output=item.get("required_output"), timeout=int(item.get("timeout", 300)),
            ))
        if not gates:
            raise ValueError("acceptance specification must define at least one gate")
        return cls(path, gates, [str(x) for x in raw.get("required_evidence", [])])


@dataclass(slots=True)
class AcceptanceSnapshot:
    hashes: dict[str, str]

    @classmethod
    def capture(cls, paths: list[str | Path]) -> "AcceptanceSnapshot":
        hashes={}
        for p0 in paths:
            p=Path(p0).resolve()
            if not p.exists() or not p.is_file():
                raise FileNotFoundError(p)
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        return cls(hashes)

    def changed(self) -> list[str]:
        changed=[]
        for name, digest in self.hashes.items():
            p=Path(name)
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                changed.append(name)
        return changed


class Verifier:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()

    def verify(self, spec: AcceptanceSpec, snapshot: AcceptanceSnapshot, evidence_refs: list[str]) -> VerificationReport:
        changed=snapshot.changed()
        if changed:
            return VerificationReport(Verdict.FAIL, [], evidence_refs, [f"acceptance file changed after snapshot: {p}" for p in changed])
        missing=[required for required in spec.required_evidence if not any(required in ref for ref in evidence_refs)]
        if missing:
            return VerificationReport(Verdict.BLOCKED, [], evidence_refs, [f"missing required evidence: {m}" for m in missing])
        checks=[]; reasons=[]
        shell=ShellTool(self.root, PermissionSet(["."],["."],[]), policy=ApprovalPolicy())
        for gate in spec.gates:
            try:
                result=shell.execute({"command":gate.command,"timeout":gate.timeout})
            except (SecurityError, TimeoutError) as exc:
                return VerificationReport(Verdict.BLOCKED, checks, evidence_refs, [f"gate {gate.name} blocked: {exc}"])
            output_ok = gate.required_output is None or gate.required_output in (result.stdout + result.stderr)
            passed = result.returncode == gate.expected_exit and output_ok
            checks.append({
                "name":gate.name,"passed":passed,"returncode":result.returncode,
                "expected_exit":gate.expected_exit,"required_output":gate.required_output,
                "stdout":result.stdout[-4000:],"stderr":result.stderr[-4000:],
            })
            if not passed:
                reasons.append(f"gate {gate.name} failed")
        verdict=Verdict.PASS if all(c["passed"] for c in checks) else Verdict.FAIL
        return VerificationReport(verdict, checks, evidence_refs, reasons)
