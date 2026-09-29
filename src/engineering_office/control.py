from __future__ import annotations
from pathlib import Path
import json


class OfficeControl:
    def __init__(self,path: str | Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists(): self._write({"paused":False,"stopped":False})
    def _write(self,data): self.path.write_text(json.dumps(data,indent=2,sort_keys=True))
    def state(self):
        try: return json.loads(self.path.read_text())
        except Exception: return {"paused":False,"stopped":False}
    def pause(self):
        s=self.state(); s["paused"]=True; self._write(s)
    def stop(self):
        s=self.state(); s["stopped"]=True; self._write(s)
    def resume(self): self._write({"paused":False,"stopped":False})
