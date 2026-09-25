"""Loads the Liquid AI model from Hugging Face and checks it returns JSON. First run downloads the weights."""
import os,sys,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from devtrace.integrations.liquid import LiquidReasoner
t=time.time(); r=LiquidReasoner()
print("model:",r.model_id,f"loaded in {time.time()-t:.1f}s")
t=time.time()
print(r.ask_json('Return JSON: {"status":"DEVTRACE_LIQUID_OK"}',"ping"))
print("usage:",r.take_usage(),f"{time.time()-t:.1f}s")
