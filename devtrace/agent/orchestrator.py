import hashlib, time
from datetime import datetime,timezone
from devtrace.agent.state_editor import StateEditor
from devtrace.store import Store

def now(): return datetime.now(timezone.utc).isoformat()

class Orchestrator:
    def __init__(self,topic,reasoner,nimble,rawtree,github,store=None,log=print):
        self.topic=topic; self.reasoner=reasoner; self.nimble=nimble
        self.rawtree=rawtree; self.github=github
        self.editor=StateEditor(reasoner); self.store=store or Store(topic); self.log=log
        self.state=self.store.load_state()

    def _event(self,event_type,warnings,**fields):
        s=self.state
        row={"timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),"event_type":event_type,"topic":self.topic,"cycle":s.cycle,
             "evidence_count":s.evidence_count,"active_fact_count":len(s.active_facts),
             "active_change_count":len(s.active_changes),"open_question_count":len(s.open_questions),
             "stale_claim_count":len(s.stale_claims),"impacted_file_count":len(s.impacted_files),
             "working_state_size":s.size(),"archived_count":s.archived_count}
        row.update(fields)
        try: self.rawtree.insert("devtrace_events",row)
        except Exception as e: warnings.append(f"rawtree {event_type}: {e}")

    def run_cycle(self,question=None,observations=None):
        t0=time.time(); warnings=[]; cycle=self.state.cycle+1
        self.log(f"[cycle {cycle}] selecting question")

        plan={"question":question,"reason":"provided by operator"} if question else self.editor.next_question(self.state)
        q=plan["question"]
        self.log(f"[cycle {cycle}] Q: {q}")
        self._event("question_selected",warnings,question=q,cycle=cycle)

        if observations is None: observations=self.nimble.search(q)
        seen=self.store.seen_evidence_ids()
        rows=[]; obs=[]
        for x in observations:
            eid=hashlib.sha256(f'{x.get("title","")}|{x.get("url","")}|{x.get("snippet","")}'.encode()).hexdigest()[:16]
            obs.append({"evidence_id":eid,"title":x.get("title",""),"url":x.get("url",""),
                        "snippet":x.get("snippet","")[:1200],"already_seen":eid in seen})
            if eid not in seen:
                rows.append({"evidence_id":eid,"topic":self.topic,"cycle":cycle,"question":q,
                             "title":x.get("title",""),"url":x.get("url",""),"snippet":x.get("snippet",""),
                             "observed_at":now(),"source":"nimble"})
        if rows:
            self.store.add_evidence(rows)
            try: self.rawtree.insert("devtrace_evidence",rows)
            except Exception as e: warnings.append(f"rawtree evidence: {e}")
        self.log(f"[cycle {cycle}] {len(observations)} observations, {len(rows)} new")

        recalled=self.store.recall(q,exclude={o["evidence_id"] for o in obs})
        new,dropped=self.editor.edit(self.state,cycle,q,obs,recalled)
        new.evidence_count=self.state.evidence_count+len(rows)
        new.archived_count=self.state.archived_count+len(dropped)
        if dropped:
            self.store.archive(dropped)
            try: self.rawtree.insert("devtrace_archive",dropped)
            except Exception as e: warnings.append(f"rawtree archive: {e}")

        impact={"enabled":False,"matches":[]}
        try:
            impact=self.github.search_code(new.code_signals+[self.topic])
            if impact.get("enabled"): new.impacted_files=impact["matches"]
        except Exception as e: warnings.append(f"github: {e}")

        new.last_updated=now()
        self.state=new
        self.store.save_state(new)
        usage=self.reasoner.take_usage() if hasattr(self.reasoner,"take_usage") else {}
        self._event("state_compacted",warnings,question=q,new_evidence_count=len(rows),
                    recalled_count=len(recalled),dropped_count=len(dropped),
                    input_tokens=usage.get("inputTokens",0),output_tokens=usage.get("outputTokens",0))
        if new.impacted_files: self._event("impact_detected",warnings,question=q)

        summary={"cycle":cycle,"timestamp":now(),"question":q,"reason":plan.get("reason",""),
                 "observations":len(observations),"new_evidence":len(rows),"recalled":len(recalled),
                 "dropped":len(dropped),"working_state_size":new.size(),"evidence_total":new.evidence_count,
                 "impacted_files":[m["path"] for m in new.impacted_files],"usage":usage,
                 "seconds":round(time.time()-t0,1),"warnings":warnings}
        self.store.log_cycle(summary)
        for w in warnings: self.log(f"[cycle {cycle}] warning: {w}")
        self.log(f"[cycle {cycle}] done: evidence={new.evidence_count} state={new.size()} "
                 f"archived={new.archived_count} impacted={len(new.impacted_files)}")
        return {"summary":summary,"github_impact":impact,"dropped":dropped,"state":new.compact()}

    def run(self,cycles=None,interval=0,stop=None):
        """Autonomous loop. cycles=None runs until stop is set."""
        n=0
        while cycles is None or n<cycles:
            if stop is not None and stop.is_set(): break
            try: self.run_cycle()
            except Exception as e: self.log(f"[cycle {self.state.cycle+1}] failed: {e}")
            n+=1
            if interval and (cycles is None or n<cycles):
                if stop is not None:
                    if stop.wait(interval): break
                else: time.sleep(interval)
        return self.state
