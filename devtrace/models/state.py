from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field

def now_iso(): return datetime.now(timezone.utc).isoformat()

class WorkingState(BaseModel):
    """Bounded, mutable working context. Raw evidence lives outside (RawTree + local mirror)."""
    topic: str
    cycle: int=0
    active_facts: List[str]=Field(default_factory=list)
    active_changes: List[str]=Field(default_factory=list)
    hypotheses: List[str]=Field(default_factory=list)
    open_questions: List[str]=Field(default_factory=list)
    stale_claims: List[str]=Field(default_factory=list)
    code_signals: List[str]=Field(default_factory=list)
    impacted_files: List[dict]=Field(default_factory=list)
    recent_questions: List[str]=Field(default_factory=list)
    evidence_count: int=0
    archived_count: int=0
    next_action: str=""
    last_updated: str=Field(default_factory=now_iso)

    def compact(self):
        return self.model_dump()

    def prompt_view(self):
        """What the model sees: bounded lists and counts only, never the evidence itself."""
        d=self.model_dump(exclude={"last_updated"})
        d["impacted_files"]=[{"path":x.get("path"),"signals":x.get("signals",[])} for x in self.impacted_files]
        return d

    def size(self):
        return sum(len(getattr(self,k)) for k in
                   ("active_facts","active_changes","hypotheses","open_questions","stale_claims"))
