"""Live dashboard + control API for the autonomous loop.

  PYTHONPATH=. uvicorn devtrace.server:app --reload
"""
import json, os, re, threading
from collections import deque
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from devtrace.store import Store, topics

app=FastAPI(title="DevTrace")
RUNNERS={}  # topic -> {"thread","stop","logs"}

class RunReq(BaseModel):
    topic: str
    cycles: Optional[int]=None   # None = run until stopped
    interval: int=60
    question: Optional[str]=None

def _running(topic):
    r=RUNNERS.get(topic); return bool(r and r["thread"].is_alive())

@app.get("/api/topics")
def api_topics():
    return {"topics":sorted(set(topics())|set(RUNNERS))}

@app.get("/api/state")
def api_state(topic:str):
    st=Store(topic); r=RUNNERS.get(topic); state=st.load_state().compact()
    # resolve the [evidence_id] citations used in the state to their source pages
    ids=set(re.findall(r"\[([0-9a-f]{16})\]",json.dumps(state)))
    sources={e["evidence_id"]:{"title":e.get("title",""),"url":e.get("url","")}
             for e in st.evidence() if e["evidence_id"] in ids}
    return {"state":state,"cycles":st.cycles(),"archive":st.archived()[-30:],"sources":sources,
            "running":_running(topic),"logs":list(r["logs"]) if r else []}

@app.post("/api/run")
def api_run(req:RunReq):
    if _running(req.topic): raise HTTPException(409,"already running")
    from devtrace.cli import build
    logs=deque(maxlen=200); stop=threading.Event()
    try: o=build(req.topic)
    except Exception as e: raise HTTPException(500,f"setup failed: {e}")
    o.log=logs.append
    def work():
        try:
            n=req.cycles
            if req.question:
                o.run_cycle(req.question)
                n=None if n is None else n-1
            if n is None or n>0: o.run(n,req.interval,stop)
        except Exception as e: logs.append(f"stopped: {e}")
        logs.append("loop finished")
    t=threading.Thread(target=work,daemon=True)
    RUNNERS[req.topic]={"thread":t,"stop":stop,"logs":logs}
    t.start()
    return {"started":req.topic}

@app.post("/api/stop")
def api_stop(topic:str):
    r=RUNNERS.get(topic)
    if r: r["stop"].set()
    return {"stopping":topic}

@app.post("/api/reset")
def api_reset(topic:str):
    """Fresh local state for a demo. Evidence already sent to RawTree is not touched."""
    if _running(topic): raise HTTPException(409,"stop the loop first")
    Store(topic).reset(); RUNNERS.pop(topic,None)
    return {"reset":topic}

@app.get("/",response_class=HTMLResponse)
def home():
    with open(os.path.join(os.path.dirname(__file__),"static","index.html"),encoding="utf8") as f: return f.read()
