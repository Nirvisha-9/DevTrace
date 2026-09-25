"""Offline tests for the long-horizon loop. Fakes stand in for live services — not for demo use.

  PYTHONPATH=. python3 -m pytest tests -q     (or: PYTHONPATH=. python3 tests/test_loop.py)
"""
import json, re, tempfile
from devtrace.agent.orchestrator import Orchestrator
from devtrace.integrations.github import GitHubClient
from devtrace.store import Store

class FakeReasoner:
    def __init__(self): self.calls=[]; self.n=0
    def take_usage(self): return {"inputTokens":10,"outputTokens":5,"calls":2}
    def ask_json(self,system,user):
        self.calls.append(user)
        if "next web investigation question" in system:
            self.n+=1
            return {"question":"stripe deprecations","reason":"model keeps repeating itself"}
        c=len([x for x in self.calls if isinstance(x,str) and x.startswith("## Current")])
        return {"new_facts":[f"finding{c}n{i} detail{c}n{i}" for i in range(10)],
                "new_changes":[{"text":"PaymentIntent.confirm_legacy removed in v10"}],
                "new_hypotheses":["checkout.py uses confirm_legacy"],
                "new_questions":[f"what replaces confirm_legacy? ({c})"],
                "stale":[{"id":"F1","because":"replaced by newer release ["+re.search(r'"evidence_id": "(\w+)"',user).group(1)+"]"}] if c>1 else [],
                "resolved":["Q1"] if c>1 else [],
                "code_signals":["confirm_legacy","stripe"],"next_action":"check migration guide"}

class FakeNimble:
    def __init__(self): self.i=0
    def search(self,q):
        self.i+=1
        return [{"title":"Stripe changelog","url":"https://x/changelog","snippet":"confirm_legacy removed"},
                {"title":f"page {self.i}","url":f"https://x/{self.i}","snippet":f"stripe deprecations {self.i}"}]

class Sink:
    def __init__(self): self.rows=[]
    def insert(self,table,rows): self.rows.append((table,rows))
    def ingest(self,e): self.rows.append(e)

class FakeGitHub(GitHubClient):
    def enabled(self): return True
    def _load(self):
        self._sha="abc"
        self._files={"app/checkout.py":"import stripe\nstripe.PaymentIntent.confirm_legacy(id)\n","README.md":"x"}

def make(tmp):
    return Orchestrator("stripe",FakeReasoner(),FakeNimble(),Sink(),FakeGitHub(),store=Store("stripe",tmp),log=lambda m:None)

def test_multi_cycle_bounded_and_persistent():
    tmp=tempfile.mkdtemp()
    o=make(tmp); o.run(3)
    s=o.state
    assert s.cycle==3
    assert len(s.active_facts)==12                      # bounded
    assert s.evidence_count==4                           # changelog deduped across cycles: 2 + 1 + 1
    assert s.archived_count>0                            # compacted items archived, not lost
    assert any(a["reason"]=="stale" for a in o.store.archived())
    assert s.active_changes==["PaymentIntent.confirm_legacy removed in v10"]   # dict -> str
    assert s.impacted_files[0]["path"]=="app/checkout.py"
    assert s.impacted_files[0]["hits"][0]=={"line":2,"signal":"confirm_legacy","code":"stripe.PaymentIntent.confirm_legacy(id)"}
    assert len(s.recent_questions)==3 and len(set(s.recent_questions))==3    # repeated question replaced
    # prompt never contains the raw evidence store, only this cycle's observations
    edit=[c for c in o.reasoner.calls if c.startswith("## Current")][-1]
    assert "evidence_refs" not in edit and "evidence_count" not in edit.split("## Question")[0]
    # a new process resumes from disk
    o2=make(tmp); assert o2.state.cycle==3
    o2.run_cycle(); assert o2.state.cycle==4
    assert len(o2.store.cycles())==4 and len(o2.store.snapshots())==4

def test_recall_brings_back_old_evidence():
    tmp=tempfile.mkdtemp()
    o=make(tmp); o.run(2)
    got=o.store.recall("stripe deprecations 1")
    assert any(r["title"]=="page 1" for r in got)

def test_rawtree_failure_is_a_warning_and_local_copy_kept():
    class Boom:
        def insert(self,t,rows): raise RuntimeError("down")
    tmp=tempfile.mkdtemp()
    o=make(tmp); o.rawtree=Boom()
    r=o.run_cycle()
    assert r["summary"]["warnings"] and o.state.cycle==1 and len(o.store.evidence())==2

def test_events_and_evidence_go_to_rawtree():
    o=make(tempfile.mkdtemp()); o.run_cycle()
    tables=[t for t,_ in o.rawtree.rows]
    assert "devtrace_evidence" in tables and tables.count("devtrace_events")>=2
    ev=[r for t,r in o.rawtree.rows if t=="devtrace_events"]
    assert {e["event_type"] for e in ev}>={"question_selected","state_compacted"}
    assert {e["cycle"] for e in ev}=={1}          # every event of the cycle carries the same cycle number

def test_similar_question_is_replaced_by_a_fresh_subject():
    from devtrace.agent.state_editor import StateEditor
    from devtrace.models.state import WorkingState
    class R:
        def ask_json(self,s,u): return {"question":"What code changes are needed to remove payment_method_collection from GrossSettlement in v15.7.0a2?"}
    s=WorkingState(topic="stripe-python",
                   recent_questions=["What specific code changes are needed for payment_method_collection removal in v15.7.0a2?"],
                   open_questions=["How is payment_method_collection replaced?","What are the migration steps for StripeObject no longer inheriting from dict?"])
    plan=StateEditor(R()).next_question(s)
    assert plan["question"]=="What are the migration steps for StripeObject no longer inheriting from dict?"

def test_stale_needs_cited_reason_otherwise_rewording():
    from devtrace.agent.state_editor import StateEditor
    from devtrace.models.state import WorkingState
    s=WorkingState(topic="t",active_facts=["v15 requires Python 3.9 [aaaaaaaa]","payment_method_collection removed from GrossSettlement [bbbbbbbb]","StripeObject is no longer a dict"])
    new,dropped=StateEditor.merge(s,2,"q",{
        "new_facts":["Removal of payment_method_collection parameter from GrossSettlement [cccccccc]"],
        "stale":[{"id":"F1","because":"v16 requires Python 3.10 [cccccccc]"},   # cited -> stale
                 {"id":"F2","because":""},                                      # reworded -> merged
                 {"id":"F3","because":"no longer relevant"}]},                   # uncited, no rewording -> kept
        cited={"cccccccc"})
    assert new.stale_claims==["v15 requires Python 3.9 [aaaaaaaa] — superseded: v16 requires Python 3.10 [cccccccc]"]
    assert {d["reason"] for d in dropped}=={"stale","merged"}
    assert new.active_facts==["StripeObject is no longer a dict","Removal of payment_method_collection parameter from GrossSettlement [cccccccc]"]

def test_merge_stale_resolved_and_limits():
    from devtrace.agent.state_editor import StateEditor
    from devtrace.models.state import WorkingState
    s=WorkingState(topic="t",active_facts=["old fact","keep fact"],open_questions=["q1?","q2?"],code_signals=["old_api"])
    new,dropped=StateEditor.merge(s,5,"q",{
        "new_facts":["keep fact","brand new [e1]"]+[f"f{i}" for i in range(20)],
        "stale":[{"id":"f1","because":"replaced by v2"}],"resolved":["Q2"],
        "new_questions":["q1?"],"code_signals":["new_api","old_api"],"next_action":""})
    assert "old fact" not in new.active_facts and new.stale_claims==["old fact — superseded: replaced by v2"]
    assert len(new.active_facts)==12 and new.active_facts[-1]=="f19"      # capped, newest kept
    assert new.open_questions==["q1?"]                                    # resolved removed, duplicate ignored
    assert {d["reason"] for d in dropped}=={"stale","resolved","compacted"}
    assert new.code_signals==["new_api","old_api"] and new.cycle==5

def test_recheck_is_scheduled_and_outcome_recorded():
    from devtrace.agent.state_editor import StateEditor
    from devtrace.models.state import WorkingState
    s=WorkingState(topic="stripe-python",cycle=5,active_facts=["old fact [aaaaaaaaaaaaaaaa]","fresh fact"],
                   added={"old fact [aaaaaaaaaaaaaaaa]":1,"fresh fact":5})
    plan=StateEditor(None).next_question(s)                       # round 6, VERIFY_EVERY=3 -> re-check
    assert plan["kind"]=="recheck" and plan["verify"]=="old fact [aaaaaaaaaaaaaaaa]"
    assert "[aaaa" not in plan["question"]
    new,_=StateEditor.merge(s,6,plan["question"],{"confirmed":["F1"]},cited={"b"*16},verify=plan["verify"])
    assert new.last_check["outcome"]=="confirmed" and new.checked["old fact [aaaaaaaaaaaaaaaa]"]==6
    assert StateEditor.due_check(new,9) is None or StateEditor.due_check(new,9)=="fresh fact"
    new2,d=StateEditor.merge(s,6,"q",{"stale":[{"id":"F1","because":"replaced in v16 ["+"b"*16+"]"}]},
                             cited={"b"*16},verify="old fact [aaaaaaaaaaaaaaaa]")
    assert new2.last_check["outcome"]=="corrected"

def test_user_question_goes_first_and_is_consumed():
    o=make(tempfile.mkdtemp())
    o.ask_to_research("Does v15 break dict access?")
    r=o.run_cycle()
    assert r["summary"]["question"]=="Does v15 break dict access?" and r["summary"]["kind"]=="user"
    assert o.state.inbox==[] and o.store.load_state().inbox==[]

def test_new_items_tracked_and_prose_signals_dropped():
    o=make(tempfile.mkdtemp()); o.run_cycle(); o.run_cycle()
    s=o.state
    assert all(c in (1,2) for c in s.added.values()) and 2 in s.added.values()
    from devtrace.agent.state_editor import _signals
    assert _signals(["description field removal","stripe.StripeObject","`one_time_fees`"])==["stripe.StripeObject","one_time_fees"]

def test_second_runner_on_same_topic_is_refused():
    tmp=tempfile.mkdtemp(); a=make(tmp); b=make(tmp)
    held=a.store.try_lock()
    try:
        try: b.run_cycle(); assert False,"should refuse"
        except RuntimeError as e: assert "already being run" in str(e)
    finally: held.close()
    b.run_cycle(); a.run_cycle()                     # a picks up b's round instead of forking history
    assert a.state.cycle==2 and [c["cycle"] for c in a.store.cycles()]==[1,2]

if __name__=="__main__":
    for k,v in list(globals().items()):
        if k.startswith("test_"): v(); print("ok",k)
