import requests
from devtrace.config import RAWTREE_API_KEY, RAWTREE_BASE_URL

def _check(r):
    if r.status_code>=400: raise RuntimeError(f"RawTree HTTP {r.status_code}: {r.text[:300]}")
    return r.json()

class RawTreeClient:
    def __init__(self):
        self.key=RAWTREE_API_KEY
        self.base=RAWTREE_BASE_URL
    def insert(self, table, rows):
        if not self.key: raise RuntimeError("RAWTREE_API_KEY missing")
        if isinstance(rows,dict): rows=[rows]
        r=requests.post(
            f"{self.base}/v1/tables/{table}",
            headers={"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},
            json=rows, timeout=30)
        return _check(r)
    def query(self, sql):
        if not self.key: raise RuntimeError("RAWTREE_API_KEY missing")
        r=requests.post(
            f"{self.base}/v1/query",
            headers={"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},
            json={"sql":sql}, timeout=30)
        return _check(r)
