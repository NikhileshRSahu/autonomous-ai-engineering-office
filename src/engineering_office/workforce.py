from __future__ import annotations
from enum import Enum
from .models import Complexity

class WorkforceDecision(str,Enum): RETAIN="RETAIN"; COACH="COACH"; REPLACE="REPLACE"

class WorkforceManager:
    def assess(self,metrics: dict) -> WorkforceDecision:
        tasks=int(metrics.get("tasks",0)); false=float(metrics.get("false_pass_rate",0)); success=float(metrics.get("verified_success_rate",0))
        if tasks>=1 and false>0: return WorkforceDecision.REPLACE
        if tasks>=3 and success<0.5: return WorkforceDecision.COACH
        return WorkforceDecision.RETAIN


def effective_complexity(base: Complexity,metrics: dict) -> Complexity:
    tasks=int(metrics.get("tasks",0)); false=float(metrics.get("false_pass_rate",0)); success=float(metrics.get("verified_success_rate",0))
    order=[Complexity.LOW,Complexity.MEDIUM,Complexity.HIGH,Complexity.ESCALATION]
    idx=order.index(base)
    if false>0 or (tasks>=3 and success<0.5): idx=min(idx+1,len(order)-1)
    return order[idx]
