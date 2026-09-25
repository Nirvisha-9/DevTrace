import json, re
from devtrace.config import (MAX_ACTIVE_FACTS,MAX_ACTIVE_CHANGES,MAX_HYPOTHESES,MAX_OPEN_QUESTIONS,
                             MAX_RECENT_QUESTIONS)

LIMITS={"active_facts":MAX_ACTIVE_FACTS,"active_changes":MAX_ACTIVE_CHANGES,"hypotheses":MAX_HYPOTHESES,
        "open_questions":MAX_OPEN_QUESTIONS,"stale_claims":MAX_OPEN_QUESTIONS,"code_signals":15}

ROLE=("You are DevTrace, an autonomous long-horizon developer agent. You continuously track real ecosystem "
      "changes (SDKs, APIs, documentation, deprecations, releases, migration requirements) for one topic and "
      "maintain a compact, evolving understanding of what matters to a codebase.")

def _strs(xs):
    out=[]
    for x in xs or []:
        if isinstance(x,dict): x=x.get("text") or x.get("claim") or x.get("question") or json.dumps(x)
        x=re.sub(r"\s*\[[FCHQ]\d+\]","",str(x)).strip()   # the model sometimes echoes internal ids
        x=re.sub(r"\s+-\s+need to .*$","",x).strip()
        if x and x not in out: out.append(x)
    return out

PREFIX={"active_facts":"F","active_changes":"C","hypotheses":"H","open_questions":"Q"}

EDIT_TASK="""Report ONLY what is new, as JSON. The code merges it into the state and enforces the limits.
- new_facts: concrete facts from the new observations, citing the evidence_id like [a1].
- new_changes: deprecations, removals, breaking changes, releases or migration requirements, with versions.
- new_hypotheses: how these changes could break a codebase that uses the topic.
- new_questions: what is still unknown and worth searching next.
- stale: ONLY ids of current items (F1, C2, H1, Q3...) that a new observation proves wrong or outdated. "because" must say what replaced it and cite that evidence_id like [a1]. Rewording or adding detail is NOT stale.
- resolved: ids of open questions (Q...) that the new observations answer.
- code_signals: exact identifiers affected code would contain: package, module, class, function, config key, version.
- next_action: one sentence.
Do not repeat items already in the current state. If the observations contain changes, new_facts/new_changes must NOT be empty.

Example (different topic; current state had F1 "requests supports Python 3.7+" and Q1 "Does requests 3.0 drop Python 3.8?"):
{"new_facts":["requests 3.0 requires Python 3.9+ [e7]"],
"new_changes":["requests 3.0: removed requests.packages alias; import urllib3 directly [e7]"],
"new_hypotheses":["code importing requests.packages.urllib3 will fail after upgrading to 3.0"],
"new_questions":["Is there a migration guide for requests 3.0 session adapters?"],
"stale":[{"id":"F1","because":"requests 3.0 requires Python 3.9+ [e7]"}],
"resolved":["Q1"],
"code_signals":["requests.packages","urllib3","requests>=3"],
"next_action":"Search the requests 3.0 migration guide for adapter changes."}"""

def _numbered(state):
    return {k:{f"{p}{i+1}":x for i,x in enumerate(getattr(state,k))} for k,p in PREFIX.items()}

def _norm(q): return " ".join(q.lower().split())

STOP=set("""what which how why when where who is are was were be been do does did the a an of to in on for from by with
and or any there that this these those it its will would should can could need needed required specific code change
changes new latest about into than then also more other their them using use used""".split())
VERSION=re.compile(r"^v?\d+(\.\w+)*$")

def _terms(s):
    s=re.sub(r"\[[0-9a-f]{6,}\]","",s)            # drop evidence ids
    return {w for w in re.findall(r"[a-z0-9_.]+",s.lower()) if len(w)>2 and w not in STOP}

def _idents(s):
    """Code-like identifiers (snake_case, dotted paths, CamelCase), excluding plain version numbers."""
    out=set()
    for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*",s):
        w=w.strip(".")
        if ("_" in w or "." in w or re.search(r"[a-z][A-Z]",w)) and not VERSION.match(w.lower()): out.add(w.lower())
    return out

def similar(a,b,threshold=0.5):
    """Same subject: most content words shared, or the same code identifier."""
    ta,tb=_terms(a),_terms(b)
    if ta and tb and len(ta&tb)/len(ta|tb)>=threshold: return True
    return bool(_idents(a)&_idents(b))

class StateEditor:
    def __init__(self,reasoner): self.reasoner=reasoner

    def next_question(self,state):
        plan=self.reasoner.ask_json(
            ROLE+" Choose the single highest-value next web investigation question. Prefer open questions and "
                 "changes most likely to affect the codebase (see impacted_files). On a fresh state, start with "
                 "the latest releases, deprecations and breaking changes for the topic. The question MUST be about "
                 "a different subject than every entry in recent_questions. Return JSON: "
                 "{\"question\":\"...\",\"reason\":\"...\"}.",
            json.dumps(state.prompt_view()))
        q=str(plan.get("question","")).strip()
        recent=state.recent_questions
        if not q or any(similar(q,r) for r in recent):
            # Model circled back to a subject it just covered: move on to something it hasn't asked about.
            t=state.topic
            pool=state.open_questions+[f"{t} migration guide",f"{t} deprecation warnings",
                                       f"{t} changelog latest release",f"{t} security advisories",
                                       f"{t} upgrade breaking issues github"]
            fresh=[x for x in pool if not any(similar(x,r) for r in recent)]
            q=fresh[0] if fresh else f"{t} release notes {len(recent)}"
            plan={"question":q,"reason":"moved on: the model's pick repeated a recent subject"}
        return plan

    def edit(self,state,cycle,question,observations,recalled):
        # The model only extracts deltas (new items + ids that went stale); merging, limits and
        # archiving are deterministic. Small local models can't reliably rewrite a whole state,
        # and this keeps working context bounded no matter what the model returns.
        view=state.prompt_view()
        for k in PREFIX: view.pop(k)
        prompt=("## Current working state\n"+json.dumps({**_numbered(state),"stale_claims":state.stale_claims,
                                                          "impacted_files":view["impacted_files"]},indent=1)+
                "\n\n## Question just investigated\n"+question+
                "\n\n## New observations from the web\n"+json.dumps(observations,indent=1)+
                "\n\n## Older evidence recalled from memory\n"+json.dumps(recalled,indent=1)+
                "\n\n## Task\n"+EDIT_TASK)
        r=self.reasoner.ask_json(ROLE+" You maintain a compact working state; raw evidence is stored "
                                 "elsewhere, so never copy observations wholesale.",prompt)
        cited={o["evidence_id"] for o in observations}|{o["evidence_id"] for o in recalled}
        return self.merge(state,cycle,question,r,cited)

    @staticmethod
    def merge(state,cycle,question,r,cited=None):
        """Apply model deltas to the state. Anything leaving working context is returned for archiving.

        A stale mark is accepted only with a reason that cites this cycle's evidence (when `cited` is given);
        otherwise it is treated as a rewording: the old item is merged into its new wording if there is
        one, or kept."""
        new=state.model_copy(deep=True); dropped=[]
        def drop(field,item,reason): dropped.append({"cycle":cycle,"topic":state.topic,"field":field,"item":item,"reason":reason})
        stale={}
        for x in r.get("stale") or []:
            if isinstance(x,dict) and x.get("id"): stale[str(x["id"]).strip().upper()]=str(x.get("because",""))
            elif isinstance(x,str): stale[x.strip().upper()]=""
        resolved={str(x).strip().upper() for x in r.get("resolved") or []}
        ids=_numbered(state)
        for k,key in (("active_facts","new_facts"),("active_changes","new_changes"),
                      ("hypotheses","new_hypotheses"),("open_questions","new_questions")):
            incoming=_strs(r.get(key)); kept=[]
            for i,x in ids[k].items():
                if i in stale:
                    why=stale[i]
                    ok=len(why.split())>=3 and (cited is None or any(e in why for e in cited))
                    if ok:
                        drop(k,x,"stale"); new.stale_claims.append(f"{x} — superseded: {why}")
                    elif any(similar(x,y,0.5) and not _idents(x)-_idents(y) for y in incoming):
                        drop(k,x,"merged")       # reworded, not disproven
                    else: kept.append(x)
                elif i in resolved: drop(k,x,"resolved")
                else: kept.append(x)
            for x in incoming:
                if not any(_norm(x)==_norm(y) or similar(x,y,0.7) for y in kept): kept.append(x)
            over=len(kept)-LIMITS[k]
            if over>0:   # oldest items leave working context first
                for x in kept[:over]: drop(k,x,"compacted")
                kept=kept[over:]
            setattr(new,k,kept)
        extra=len(new.stale_claims)-LIMITS["stale_claims"]
        if extra>0:
            for x in new.stale_claims[:extra]: drop("stale_claims",x,"compacted")
            new.stale_claims=new.stale_claims[extra:]
        sig=_strs(r.get("code_signals"))+[x for x in state.code_signals]
        new.code_signals=list(dict.fromkeys(sig))[:LIMITS["code_signals"]]
        new.next_action=str(r.get("next_action","")) or state.next_action
        new.cycle=cycle
        new.recent_questions=(state.recent_questions+[question])[-MAX_RECENT_QUESTIONS:]
        return new,dropped
