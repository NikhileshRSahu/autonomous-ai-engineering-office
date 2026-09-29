from __future__ import annotations
from dataclasses import asdict,dataclass
from pathlib import Path
import json,time,uuid

@dataclass(slots=True)
class DecisionRecord:
    decision_id:str; question:str; options:list[str]; selected:str; reason:str; evidence:list[str]; risks:list[str]; created_at:float

class DecisionLog:
    def __init__(self,root: str|Path): self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def record(self,question,options,selected,reason,evidence,risks):
        rec=DecisionRecord(f"D-{uuid.uuid4().hex[:10]}",question,list(options),selected,reason,list(evidence),list(risks),time.time())
        (self.root/f"{rec.decision_id}.json").write_text(json.dumps(asdict(rec),indent=2,sort_keys=True)); return rec
    def get(self,decision_id): return DecisionRecord(**json.loads((self.root/f"{decision_id}.json").read_text()))
    def list(self): return [DecisionRecord(**json.loads(p.read_text())) for p in sorted(self.root.glob("D-*.json"))]
