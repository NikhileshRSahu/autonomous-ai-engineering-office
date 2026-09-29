from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import threading
import time
import uuid

from .security import ApprovalPolicy


@dataclass(slots=True)
class ApprovalRequest:
    approval_id: str
    action: str
    risk_class: str
    reason: str
    status: str
    created_at: float
    decided_at: float | None = None


class ApprovalManager:
    def __init__(self, path: str | Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.Lock()
        if not self.path.exists(): self.path.write_text("[]")

    def _load(self) -> list[ApprovalRequest]:
        try: raw=json.loads(self.path.read_text())
        except json.JSONDecodeError: raw=[]
        return [ApprovalRequest(**x) for x in raw]

    def _save(self, items: list[ApprovalRequest]) -> None:
        self.path.write_text(json.dumps([asdict(x) for x in items],indent=2,sort_keys=True))

    def request(self, action: str, risk_class: str, reason: str) -> ApprovalRequest:
        with self._lock:
            items=self._load()
            for item in items:
                if item.action==action and item.risk_class==risk_class and item.status=="PENDING":
                    return item
            req=ApprovalRequest(f"APR-{uuid.uuid4().hex[:10]}",action,risk_class,reason,"PENDING",time.time())
            items.append(req); self._save(items); return req

    def _decide(self, approval_id: str, status: str) -> ApprovalRequest:
        with self._lock:
            items=self._load()
            for item in items:
                if item.approval_id==approval_id:
                    item.status=status; item.decided_at=time.time(); self._save(items); return item
            raise KeyError(approval_id)

    def approve(self, approval_id: str) -> ApprovalRequest:
        return self._decide(approval_id,"APPROVED")

    def deny(self, approval_id: str) -> ApprovalRequest:
        return self._decide(approval_id,"DENIED")

    def list(self, status: str | None = None) -> list[ApprovalRequest]:
        items=self._load()
        return [x for x in items if status is None or x.status==status]

    def policy(self) -> ApprovalPolicy:
        approved={x.action for x in self._load() if x.status=="APPROVED"}
        return ApprovalPolicy(auto_mode=True, approved_actions=approved)
