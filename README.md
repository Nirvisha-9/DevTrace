# DevTrace v2

**An autonomous long-horizon developer agent that continuously tracks real ecosystem changes and maintains a compact, evolving understanding of what matters to a codebase.**

Built for the Long Horizon Agents Hackathon.

## The problem

Developer ecosystems change continuously. Developers cannot continuously monitor SDKs, APIs, documentation, deprecations, releases and migration requirements — and understand which changes actually affect their code.

## What DevTrace does

Give DevTrace a topic (an SDK, API or framework your code depends on) and a GitHub repo. It then runs on its own:

1. **Chooses its next question** — the highest-value unresolved thing to investigate.
2. **Observes the real web** — searches live docs, changelogs and release notes via Nimble.
3. **Keeps every piece of evidence** — raw observations are stored permanently in RawTree.
4. **Edits a bounded working state** — a Liquid AI model (LFM2.5-2.6B, running locally) reports what's new and which existing items are now stale; the code merges that into a compact state (at most 12 facts, 8 changes, 5 hypotheses, 5 open questions).
5. **Checks code impact** — scans the GitHub repo for code touched by the changes it found.
6. **Records how understanding evolves** — each cycle is logged to RawTree (`devtrace_events`) as a timeline.
7. **Picks the next question** — and repeats.

Irrelevant details drop out of working state but never out of evidence, so the agent stays focused over long horizons without forgetting.

## Core loop

```
REAL WEB -> NIMBLE -> RAWTREE -> LIQUID AI STATE EDITOR -> RAWTREE TIMELINE -> NEXT QUESTION -> GITHUB IMPACT
```

| Component | Role |
|---|---|
| Nimble Search API | Live web search over docs, changelogs, releases |
| RawTree (by Tinybird) | Evidence store (`devtrace_evidence`), archive (`devtrace_archive`) and cycle timeline (`devtrace_events`) |
| Liquid AI LFM2.5-2.6B (Hugging Face, local via MLX) | State editor and next-question selection |
| GitHub | Codebase impact inspection |

## Long-horizon design

- **Persistent state** — working state is saved to `.devtrace/<topic>/` after every cycle, so the agent resumes where it left off across restarts.
- **Model extracts, code merges** — the model only returns deltas (new items, stale/resolved ids); limits, merging and archiving are enforced in code, so context stays bounded whatever the model outputs.
- **Bounded context** — the model only ever sees capped lists and counts, never the raw evidence. Evidence grows; working context doesn't.
- **Archive, don't delete** — anything that leaves working state (compacted or stale) is written to `archive.jsonl` and RawTree `devtrace_archive`.
- **Recall** — when a new question overlaps older evidence, that evidence is brought back into the prompt.
- **No repeated questions** — recent questions are tracked; repeats fall back to an open question.
- **Code signals → impact** — the model extracts exact package/method/config names; the repo is downloaded once and scanned for them with file + line hits.
- **Re-checks old beliefs** — every `VERIFY_EVERY` rounds (default 3) it re-verifies its oldest fact or change and records the outcome: still true, corrected, or unclear.
- **Ask DevTrace** — ask a question in the dashboard; it answers from its summary and saved evidence, with sources, and can queue the question for the agent to research next round.
- **One runner per topic** — a per-topic lock stops the dashboard and CLI from running the same topic at once.
- **Timeline** — RawTree `devtrace_events` gets `question_selected`, `state_compacted` and `impact_detected` events per cycle, including Liquid model token usage.

## Setup

Requires an Apple Silicon Mac (the model runs locally with MLX) and Python 3.10+.

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # fill in NIMBLE_API_KEY, RAWTREE_API_KEY, GITHUB_TOKEN, GITHUB_REPO
```

Model: `LIQUID_MODEL_ID` (default `LiquidAI/LFM2.5-2.6B-MLX-8bit`, Liquid's official MLX build) is downloaded from Hugging Face on first run (~2.8 GB, a few minutes) and cached after that. No API key needed. LFM2.5 is a thinking model; DevTrace pre-fills past the thinking block so each call returns JSON directly (~20 s of model time per cycle on an M5).

Smoke tests:

```bash
.venv/bin/python scripts/liquid_smoke_test.py
.venv/bin/python scripts/rawtree_smoke_test.py
.venv/bin/python scripts/nimble_probe.py
PYTHONPATH=. .venv/bin/python -m pytest tests -q     # offline loop tests (fakes, not for demo)
```

## Run

CLI:

```bash
PYTHONPATH=. .venv/bin/python -m devtrace.cli run "stripe-python" --cycles 3 --interval 60 --reset
PYTHONPATH=. .venv/bin/python -m devtrace.cli run "stripe-python" --cycles 0 --interval 300   # forever
PYTHONPATH=. .venv/bin/python -m devtrace.cli status "stripe-python"
.venv/bin/python scripts/rawtree_timeline.py "stripe-python"                          # timeline from RawTree
```

Live dashboard (start/stop the loop, compression chart, state, code impact, archive, log):

```bash
PYTHONPATH=. .venv/bin/uvicorn devtrace.server:app
# open http://127.0.0.1:8000
```

Do not use placeholder evidence in the final demo.
