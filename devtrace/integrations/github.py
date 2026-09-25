import io, tarfile, requests
from devtrace.config import GITHUB_TOKEN,GITHUB_REPO,MAX_IMPACTED_FILES

CODE_EXT=(".py",".js",".ts",".tsx",".jsx",".mjs",".java",".go",".rs",".rb",".kt",".swift",".cs",".php",
          ".yaml",".yml",".toml",".json",".txt",".cfg",".gradle")
SKIP_DIRS=("node_modules/","vendor/","dist/","build/",".git/","__pycache__/")

class GitHubClient:
    """Downloads the repo once (tarball) and scans it in memory for code signals."""
    def __init__(self):
        self._files=None; self._sha=None

    def enabled(self): return bool(GITHUB_REPO and "/" in GITHUB_REPO)   # token optional for public repos
    def _h(self):
        h={"Accept":"application/vnd.github+json"}
        if GITHUB_TOKEN: h["Authorization"]=f"Bearer {GITHUB_TOKEN}"
        return h

    def _head_sha(self):
        r=requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/commits/HEAD",headers=self._h(),timeout=30)
        r.raise_for_status(); return r.json()["sha"]

    def _load(self):
        sha=self._head_sha()
        if self._files is not None and sha==self._sha: return
        r=requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/tarball/{sha}",headers=self._h(),timeout=120)
        r.raise_for_status()
        files={}
        with tarfile.open(fileobj=io.BytesIO(r.content),mode="r:gz") as t:
            for m in t.getmembers():
                if not m.isfile() or m.size>500_000: continue
                path=m.name.split("/",1)[1] if "/" in m.name else m.name
                if not path.endswith(CODE_EXT) or any(s in path for s in SKIP_DIRS): continue
                files[path]=t.extractfile(m).read().decode("utf-8","ignore")
        self._files=files; self._sha=sha

    def search_code(self, signals):
        signals=[s for s in dict.fromkeys(x.strip() for x in signals) if len(s)>=3]
        if not self.enabled(): return {"enabled":False,"matches":[]}
        if not signals: return {"enabled":True,"sha":self._sha,"matches":[]}
        self._load()
        matches=[]
        for path,txt in self._files.items():
            lines=txt.splitlines(); low=[l.lower() for l in lines]
            hits=[]; used=set()
            for s in signals:
                sl=s.lower()
                for i,l in enumerate(low):
                    if sl in l:
                        used.add(s)
                        if len(hits)<5: hits.append({"line":i+1,"signal":s,"code":lines[i].strip()[:200]})
            if used: matches.append({"path":path,"signals":sorted(used),"hits":hits})
        matches.sort(key=lambda m:(-len(m["signals"]),m["path"]))
        return {"enabled":True,"repo":GITHUB_REPO,"sha":self._sha,"files_scanned":len(self._files),
                "matches":matches[:MAX_IMPACTED_FILES]}
