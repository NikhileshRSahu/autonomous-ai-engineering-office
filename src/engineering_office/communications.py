from __future__ import annotations
from enum import Enum
from typing import Any, Callable
from .storage import OfficeStore


class MessageKind(str,Enum):
    ACTION="ACTION"; EXPERIMENT="EXPERIMENT"; EVIDENCE_REQUEST="EVIDENCE_REQUEST"; SPECIALIST_REQUEST="SPECIALIST_REQUEST"
    IMPLEMENTATION="IMPLEMENTATION"; BLOCKED="BLOCKED"; FINDING="FINDING"; QUESTION="QUESTION"; COMMENT="COMMENT"
    DIRECTOR_INTERVENTION="DIRECTOR_INTERVENTION"; STEER="STEER"


class CommunicationManager:
    ACTIONABLE={MessageKind.ACTION,MessageKind.EXPERIMENT,MessageKind.EVIDENCE_REQUEST,MessageKind.SPECIALIST_REQUEST,MessageKind.IMPLEMENTATION,MessageKind.BLOCKED}
    def __init__(self,store: OfficeStore,max_non_actionable: int=3,event_sink: Callable[[str,str|None,str,str,str,dict[str,Any]],None]|None=None): self.store=store; self.max=max_non_actionable; self.event_sink=event_sink
    def send(self,project_id,task_id,sender,recipient,kind: MessageKind,data: dict[str,Any]):
        mid=self.store.add_message(project_id,task_id,sender,recipient,kind.value,data)
        if self.event_sink is not None:
            self.event_sink(project_id, task_id, sender, recipient, kind.value, data)
        msgs=self.store.list_messages(project_id,task_id)
        chatter=0
        for m in reversed(msgs):
            k=MessageKind(m["kind"])
            if k in self.ACTIONABLE or k is MessageKind.DIRECTOR_INTERVENTION: break
            chatter+=1
        intervene=chatter>self.max
        if intervene:
            self.store.add_message(project_id,task_id,"Office Director",sender,MessageKind.DIRECTOR_INTERVENTION.value,{"reason":"non-actionable discussion limit reached","required_outcome":"ACTION|EXPERIMENT|EVIDENCE_REQUEST|SPECIALIST_REQUEST|IMPLEMENTATION|BLOCKED"})
        return {"message_id":mid,"director_intervention":intervene}
