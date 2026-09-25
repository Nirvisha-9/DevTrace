"""Runs one live Nimble search and prints the normalized results."""
import os,sys,json
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from devtrace.integrations.nimble import NimbleClient
q=sys.argv[1] if len(sys.argv)>1 else "stripe-python SDK latest release notes breaking changes"
res=NimbleClient().search(q,max_results=5)
print(len(res),"results")
for x in res: print("-",x["title"],"|",x["url"],"|",x["snippet"][:150].replace("\n"," "))
