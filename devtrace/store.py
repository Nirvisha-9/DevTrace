"""Local persistence so the agent survives restarts and runs across long horizons.

Layout: .devtrace/<topic-slug>/
  state.json       current working state
  snapshots.jsonl  state after every cycle (for the timeline / compression view)
  evidence.jsonl   mirror of every observation written to RawTree
  archive.jsonl    items that left working state (dropped, never deleted)
  cycles.jsonl     per-cycle log (question, counts, token usage, warnings)
"""
import json, os, re
from devtrace.config import DATA_DIR
from devtrace.models.state import WorkingState

def slug(topic): return re.sub(r"[^a-z0-9]+","-",topic.lower()).strip("-") or "topic"

class Store:
    def __init__(self,topic,root=None):
        self.topic=topic
        self.dir=os.path.join(root or DATA_DIR,slug(topic))
        os.makedirs(self.dir,exist_ok=True)

    def _p(self,name): return os.path.join(self.dir,name)

    def _append(self,name,rows):
        with open(self._p(name),"a",encoding="utf8") as f:
            for r in rows: f.write(json.dumps(r,default=str)+"\n")

    def _read(self,name):
        if not os.path.exists(self._p(name)): return []
        with open(self._p(name),encoding="utf8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def load_state(self):
        if os.path.exists(self._p("state.json")):
            with open(self._p("state.json"),encoding="utf8") as f:
                return WorkingState(**json.load(f))
        return WorkingState(topic=self.topic)

    def save_state(self,state):
        tmp=self._p("state.json.tmp")
        with open(tmp,"w",encoding="utf8") as f: json.dump(state.compact(),f,indent=2)
        os.replace(tmp,self._p("state.json"))
        self._append("snapshots.jsonl",[state.compact()])

    def reset(self):
        for n in ("state.json","snapshots.jsonl","evidence.jsonl","archive.jsonl","cycles.jsonl"):
            if os.path.exists(self._p(n)): os.remove(self._p(n))

    def seen_evidence_ids(self): return {r["evidence_id"] for r in self._read("evidence.jsonl")}
    def add_evidence(self,rows): self._append("evidence.jsonl",rows)
    def evidence(self): return self._read("evidence.jsonl")
    def archive(self,rows): self._append("archive.jsonl",rows)
    def archived(self): return self._read("archive.jsonl")
    def log_cycle(self,row): self._append("cycles.jsonl",[row])
    def cycles(self): return self._read("cycles.jsonl")
    def snapshots(self): return self._read("snapshots.jsonl")

    def recall(self,query,exclude=(),k=5):
        """Bring older evidence back into view when a new question overlaps it."""
        words={w for w in re.findall(r"[a-z0-9_.]{3,}",query.lower())}
        if not words: return []
        scored=[]
        for r in self.evidence():
            if r["evidence_id"] in exclude: continue
            text=f'{r.get("title","")} {r.get("snippet","")}'.lower()
            s=sum(1 for w in words if w in text)
            if s: scored.append((s,r))
        scored.sort(key=lambda x:-x[0])
        return [{"evidence_id":r["evidence_id"],"title":r.get("title",""),"url":r.get("url",""),
                 "snippet":r.get("snippet","")[:400],"observed_at":r.get("observed_at"),
                 "cycle":r.get("cycle")} for _,r in scored[:k]]

def topics(root=None):
    root=root or DATA_DIR
    if not os.path.isdir(root): return []
    out=[]
    for d in sorted(os.listdir(root)):
        p=os.path.join(root,d,"state.json")
        if os.path.exists(p):
            with open(p,encoding="utf8") as f: out.append(json.load(f)["topic"])
    return out
