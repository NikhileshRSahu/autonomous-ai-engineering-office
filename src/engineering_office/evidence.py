from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import shutil
import threading


_SECRET_PATTERNS = [
    (re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s'\";]+"), lambda m: m.group(0).split(m.group(0)[m.group(0).find('=') if '=' in m.group(0) else m.group(0).find(':')])[0] + "=[REDACTED]"),
    (re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]+"), lambda _m: "Authorization: Bearer [REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), lambda _m: "[REDACTED]"),
    (re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S), lambda _m: "[REDACTED PRIVATE KEY]"),
]


def redact_secrets(text: str) -> str:
    out = text
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


@dataclass(slots=True)
class EvidenceRef:
    project_id: str
    task_id: str
    run_id: str
    name: str
    path: str
    sha256: str
    size: int
    metadata: dict[str, Any]


class EvidenceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = self.root / "index.jsonl"
        self._lock = threading.Lock()

    def _target(self, project_id: str, task_id: str, run_id: str, name: str) -> Path:
        safe_parts = [self._safe(x) for x in [project_id, task_id, run_id]]
        safe_name = Path(name).name
        target = self.root.joinpath(*safe_parts, safe_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _safe(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]", "_", value)

    def add_text(self, project_id: str, task_id: str, run_id: str, name: str, text: str, metadata: dict[str, Any] | None = None) -> EvidenceRef:
        target = self._target(project_id, task_id, run_id, name)
        target.write_text(redact_secrets(text))
        return self._index(project_id, task_id, run_id, name, target, metadata or {})

    def add_file(self, project_id: str, task_id: str, run_id: str, source: str | Path, name: str | None = None, metadata: dict[str, Any] | None = None, redact_text: bool = False) -> EvidenceRef:
        source = Path(source)
        target = self._target(project_id, task_id, run_id, name or source.name)
        if redact_text:
            target.write_text(redact_secrets(source.read_text(errors="replace")))
        else:
            shutil.copy2(source, target)
        return self._index(project_id, task_id, run_id, target.name, target, metadata or {})

    def _index(self, project_id: str, task_id: str, run_id: str, name: str, path: Path, metadata: dict[str, Any]) -> EvidenceRef:
        data = path.read_bytes()
        ref = EvidenceRef(project_id, task_id, run_id, name, str(path), hashlib.sha256(data).hexdigest(), len(data), metadata)
        with self._lock:
            with self.index.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(ref), sort_keys=True) + "\n")
        return ref

    def list_refs(self, project_id: str | None = None, task_id: str | None = None) -> list[EvidenceRef]:
        if not self.index.exists(): return []
        refs=[]
        for line in self.index.read_text().splitlines():
            d=json.loads(line)
            if project_id is not None and d["project_id"] != project_id: continue
            if task_id is not None and d["task_id"] != task_id: continue
            refs.append(EvidenceRef(**d))
        return refs
