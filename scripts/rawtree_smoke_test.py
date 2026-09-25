"""Inserts a row into RawTree and reads it back."""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from devtrace.integrations.rawtree import RawTreeClient
r=RawTreeClient(); tag=f"DEVTRACE_RAWTREE_OK_{int(time.time())}"
print(r.insert("devtrace_smoke",[{"message":tag}]))
print(r.query(f"SELECT count() AS n FROM devtrace_smoke WHERE toString(message) = '{tag}'"))
