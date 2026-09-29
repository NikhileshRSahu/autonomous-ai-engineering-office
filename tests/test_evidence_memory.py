from pathlib import Path
import hashlib

from engineering_office.evidence import EvidenceStore, redact_secrets
from engineering_office.memory import MemoryManager
from engineering_office.storage import OfficeStore


def test_evidence_hash_and_redaction(tmp_path: Path):
    store = EvidenceStore(tmp_path / "evidence")
    ref = store.add_text("P1", "T1", "run-1", "log.txt", "token=sk-abcdefghijklmnopqrstuvwxyz123456")
    saved = Path(ref.path).read_text()
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in saved
    assert "[REDACTED]" in saved
    assert ref.sha256 == hashlib.sha256(Path(ref.path).read_bytes()).hexdigest()


def test_redaction_covers_bearer_and_private_key():
    text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
    out = redact_secrets(text)
    assert "abcdefghijklmnopqrstuvwxyz" not in out
    assert "secret" not in out


def test_only_verified_fix_can_be_promoted(tmp_path: Path):
    db = OfficeStore(tmp_path / "office.db")
    memory = MemoryManager(db)
    rejected = memory.record_pattern("P1", "failure_pattern", {"symptom":"x"}, verified=False)
    assert memory.promote_success(rejected) is False
    verified = memory.record_pattern("P1", "candidate_fix", {"fix":"y"}, verified=True)
    assert memory.promote_success(verified) is True
    kinds = [m["kind"] for m in db.list_memory("P1", verified_only=True)]
    assert "successful_fix" in kinds


def test_agent_performance_is_exposed(tmp_path: Path):
    db = OfficeStore(tmp_path / "office.db")
    memory = MemoryManager(db)
    memory.record_agent_outcome("agent", True, False, 1)
    memory.record_agent_outcome("agent", False, False, 3)
    perf = memory.agent_performance("agent")
    assert perf["verified_success_rate"] == 0.5
    assert perf["false_pass_rate"] == 0.0
