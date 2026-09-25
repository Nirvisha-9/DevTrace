"""DevTrace CLI.

  python -m devtrace.cli run "stripe-python" --cycles 3 --interval 60
  python -m devtrace.cli run "stripe-python" --question "stripe-python v10 breaking changes"
  python -m devtrace.cli status "stripe-python"
  python -m devtrace.cli reset "stripe-python"
"""
import argparse,json

def reasoner():
    from devtrace.integrations.liquid import LiquidReasoner
    return LiquidReasoner()

def build(topic):
    from devtrace.integrations.nimble import NimbleClient
    from devtrace.integrations.rawtree import RawTreeClient
    from devtrace.integrations.github import GitHubClient
    from devtrace.agent.orchestrator import Orchestrator
    return Orchestrator(topic,reasoner(),NimbleClient(),RawTreeClient(),GitHubClient())

def main():
    from devtrace.store import Store
    p=argparse.ArgumentParser(prog="devtrace")
    sub=p.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("run",help="run autonomous cycles")
    r.add_argument("topic")
    r.add_argument("--cycles",type=int,default=1,help="0 = run forever")
    r.add_argument("--interval",type=int,default=0,help="seconds between cycles")
    r.add_argument("--question",help="override the first question")
    r.add_argument("--nimble-json",help="use saved Nimble output for the first cycle")
    r.add_argument("--reset",action="store_true",help="start from a fresh state")
    s=sub.add_parser("status",help="show current working state"); s.add_argument("topic")
    x=sub.add_parser("reset",help="clear local state"); x.add_argument("topic")
    a=p.parse_args()

    if a.cmd=="reset":
        Store(a.topic).reset(); print(f"reset {a.topic}"); return
    if a.cmd=="status":
        st=Store(a.topic)
        print(json.dumps({"state":st.load_state().compact(),"cycles":st.cycles()[-5:]},indent=2)); return

    if a.reset: Store(a.topic).reset()
    o=build(a.topic)
    if a.question or a.nimble_json:
        obs=None
        if a.nimble_json:
            with open(a.nimble_json,encoding="utf8") as f: obs=json.load(f)
        print(json.dumps(o.run_cycle(a.question,obs)["summary"],indent=2))
        remaining=None if a.cycles==0 else a.cycles-1
        if remaining==0: return
        o.run(remaining,a.interval)
    else:
        o.run(None if a.cycles==0 else a.cycles,a.interval)
    print(json.dumps(o.state.compact(),indent=2))

if __name__=="__main__": main()
