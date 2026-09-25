"""Prints the per-cycle timeline for a topic from RawTree (devtrace_events)."""
import json,os,sys
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,root)
from devtrace.integrations.rawtree import RawTreeClient
if len(sys.argv)<2: raise SystemExit('usage: rawtree_timeline.py "<topic>"')
topic="'"+sys.argv[1].replace("\\","\\\\").replace("'","\\'")+"'"
with open(os.path.join(root,"rawtree","timeline.sql")) as f: sql=f.read().replace("{topic}",topic).replace("{table}",os.getenv("DEVTRACE_EVENTS_TABLE","devtrace_events"))
print(json.dumps(RawTreeClient().query(sql),indent=2))
