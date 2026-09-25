"""Reasoner backed by a Liquid AI LFM model from Hugging Face, run locally on Apple Silicon with MLX.

Default: LiquidAI/LFM2.5-2.6B-MLX-8bit (Liquid's official MLX build of LFM2.5-2.6B, ~2.8 GB).
The first run downloads it to the Hugging Face cache; after that it loads in a few seconds.
The model is loaded once per process and shared.

LFM2.5 is a thinking model whose chat template always opens with <think>. For the agent's
structured calls we pre-fill "</think>\n{" so it skips thinking and must answer with JSON.
"""
import json, re, threading
from devtrace.config import LIQUID_MODEL_ID, LIQUID_MAX_NEW_TOKENS

_MODELS={}
_LOCK=threading.Lock()
PREFILL="</think>\n{"

def _extract_json(raw):
    raw=raw.strip()
    if raw.startswith("```"):
        raw=raw.split("\n",1)[1].rsplit("```",1)[0]
    try: return json.loads(raw)
    except json.JSONDecodeError: pass
    m=re.search(r"\{.*\}",raw,re.S)
    if m:
        try: return json.loads(m.group(0))
        except json.JSONDecodeError: pass
    # small models sometimes drop a comma or quote; repair instead of discarding the answer
    from json_repair import repair_json
    fixed=repair_json(raw,return_objects=True)
    if isinstance(fixed,dict) and fixed: return fixed
    raise json.JSONDecodeError("unrecoverable model output",raw,0)

def _load(model_id):
    with _LOCK:
        if model_id not in _MODELS:
            from mlx_lm import load
            _MODELS[model_id]=load(model_id)
        return _MODELS[model_id]

class LiquidReasoner:
    def __init__(self,model_id=None):
        from mlx_lm.sample_utils import make_sampler, make_logits_processors
        self.model_id=model_id or LIQUID_MODEL_ID
        self.model,self.tok=_load(self.model_id)
        # Liquid's recommended generation settings for LFM2.5
        self.sampler=make_sampler(temp=0.1,top_k=50)
        self.processors=make_logits_processors(repetition_penalty=1.1)
        self.usage={"inputTokens":0,"outputTokens":0,"calls":0}

    def _chat(self,messages):
        from mlx_lm import generate
        prompt=self.tok.apply_chat_template(messages,add_generation_prompt=True,tokenize=False)+PREFILL
        with _LOCK:   # one generation at a time on the shared model
            out=generate(self.model,self.tok,prompt=prompt,max_tokens=LIQUID_MAX_NEW_TOKENS,
                         sampler=self.sampler,logits_processors=self.processors)
        self.usage["inputTokens"]+=len(self.tok.encode(prompt))
        self.usage["outputTokens"]+=len(self.tok.encode(out))
        self.usage["calls"]+=1
        return "{"+out

    def ask_json(self, system, user, retries=1):
        messages=[{"role":"system","content":system+" Respond with a single JSON object only."},
                  {"role":"user","content":user}]
        for attempt in range(retries+1):
            raw=self._chat(messages)
            try: return _extract_json(raw)
            except (json.JSONDecodeError,IndexError):
                if attempt==retries: raise
                messages+=[{"role":"assistant","content":raw},
                           {"role":"user","content":"That was not valid JSON. Return only the JSON object."}]

    def take_usage(self):
        u=dict(self.usage); self.usage={"inputTokens":0,"outputTokens":0,"calls":0}
        return u
