import os
from dotenv import load_dotenv
load_dotenv()

def env(k, d=""): return os.getenv(k, d)

LIQUID_MODEL_ID=env("LIQUID_MODEL_ID","LiquidAI/LFM2.5-2.6B-MLX-8bit")
LIQUID_MAX_NEW_TOKENS=int(env("LIQUID_MAX_NEW_TOKENS","1800"))
NIMBLE_API_KEY=env("NIMBLE_API_KEY")
NIMBLE_CLI_BIN=env("NIMBLE_CLI_BIN","nimble")
RAWTREE_API_KEY=env("RAWTREE_API_KEY")
RAWTREE_BASE_URL=env("RAWTREE_BASE_URL","https://api.rawtree.com").rstrip("/")
GITHUB_TOKEN=env("GITHUB_TOKEN")
GITHUB_REPO=env("GITHUB_REPO")
MAX_ACTIVE_FACTS=int(env("MAX_ACTIVE_FACTS","12"))
MAX_ACTIVE_CHANGES=int(env("MAX_ACTIVE_CHANGES","8"))
MAX_HYPOTHESES=int(env("MAX_HYPOTHESES","5"))
MAX_OPEN_QUESTIONS=int(env("MAX_OPEN_QUESTIONS","5"))
VERIFY_EVERY=int(env("VERIFY_EVERY","3"))   # every Nth round re-checks the oldest belief
MAX_RECENT_QUESTIONS=int(env("MAX_RECENT_QUESTIONS","8"))
MAX_IMPACTED_FILES=int(env("MAX_IMPACTED_FILES","10"))
DATA_DIR=env("DEVTRACE_DATA_DIR",".devtrace")
