import json, shutil, subprocess, requests
from devtrace.config import NIMBLE_API_KEY, NIMBLE_CLI_BIN

SEARCH_URL="https://sdk.nimbleway.com/v2/search"

def _norm(data):
    if isinstance(data,dict): data=data.get("results",data.get("items",[data]))
    return [{"title":x.get("title",x.get("name","Nimble result")),
             "url":x.get("url",x.get("link","")),
             "snippet":x.get("content") or x.get("description") or x.get("snippet") or x.get("text","")}
            for x in data if isinstance(x,dict)]

class NimbleClient:
    """Live web search. Uses the Nimble Search API when NIMBLE_API_KEY is set, else the nimble CLI."""
    def search(self, query, max_results=10):
        if NIMBLE_API_KEY: return self._api(query,max_results)
        return self._cli(query,max_results)

    def _api(self, query, max_results):
        r=requests.post(SEARCH_URL,timeout=90,
                        headers={"Authorization":f"Bearer {NIMBLE_API_KEY}","Content-Type":"application/json"},
                        json={"query":query,"max_results":max_results})
        if r.status_code>=400: raise RuntimeError(f"Nimble HTTP {r.status_code}: {r.text[:300]}")
        return _norm(r.json())

    def _cli(self, query, max_results):
        if not shutil.which(NIMBLE_CLI_BIN):
            raise RuntimeError("Set NIMBLE_API_KEY (or install the nimble CLI).")
        p=subprocess.run(
            [NIMBLE_CLI_BIN,"search","--query",query,"--max-results",str(max_results)],
            text=True,capture_output=True,timeout=90)
        if p.returncode: raise RuntimeError(p.stderr.strip() or "Nimble search failed")
        try: data=json.loads(p.stdout)
        except json.JSONDecodeError:
            return [{"title":"Nimble search output","url":"","snippet":p.stdout.strip()}]
        return _norm(data)
