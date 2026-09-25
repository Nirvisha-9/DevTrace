"""Answer a person's question from what the agent has already learned (no new web search).

Grounding: the current working state plus the most relevant saved evidence. If the answer isn't in
there, the model says so and the question can be handed to the agent to research next round.
"""
import json, re
from devtrace.agent.state_editor import ROLE

TASK="""Answer the user's question about {topic} using ONLY the working state and saved evidence above.
- Be concise: 2-5 sentences, plain language, mention exact versions and code names when known.
- Cite the evidence_id in brackets after each claim that comes from evidence, like [a1b2c3d4e5f6a7b8].
- If the material does not contain the answer, say what is known and that it hasn't been researched yet.
Return JSON: {{"answer":"...","confidence":"high|medium|low","answered":true|false}}
("answered" is false when the material does not actually answer the question)."""

def answer(reasoner,store,state,question,k=6):
    evidence=[{"evidence_id":e["evidence_id"],"title":e["title"],"snippet":e["snippet"][:600]}
              for e in store.recall(question,k=k)]
    known={k:getattr(state,k) for k in ("active_changes","active_facts","hypotheses","stale_claims","open_questions")}
    prompt=("## Working state\n"+json.dumps(known,indent=1)+
            "\n\n## Saved evidence most related to the question\n"+json.dumps(evidence,indent=1)+
            "\n\n## Question\n"+question+"\n\n## Task\n"+TASK.format(topic=state.topic))
    r=reasoner.ask_json(ROLE+" You are answering a developer's question from your own notes.",prompt)
    text=str(r.get("answer","")).strip() or "I don't have enough information on that yet."
    valid={e["evidence_id"] for e in store.evidence()}
    cited=[c for c in dict.fromkeys(re.findall(r"\[([0-9a-f]{16})\]",text)) if c in valid]
    text=re.sub(r"\s*\[([0-9a-f]{16})\]",lambda m:f" [{m.group(1)}]" if m.group(1) in valid else "",text)
    answered=bool(r.get("answered",True)) and bool(cited or known["active_facts"] or known["active_changes"])
    if not answered:                                       # no citations on "not covered" replies
        cited=[]; text=re.sub(r",?\s*\[[0-9a-f]{16}\],?","",text)
    conf=str(r.get("confidence","medium")).lower()
    if conf not in ("high","medium","low"): conf="medium"
    if not cited and conf=="high": conf="medium"          # never claim high confidence without a source
    return {"answer":text,"confidence":conf,"answered":answered,"cited":cited,
            "usage":reasoner.take_usage() if hasattr(reasoner,"take_usage") else {}}
