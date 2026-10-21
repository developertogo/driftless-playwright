import os
from pathlib import Path

# Set browser-use config paths before any imports
if "BROWSER_USE_CONFIG_DIR" not in os.environ:
    os.environ["BROWSER_USE_CONFIG_DIR"] = "/tmp/browseruse"

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "sessions"
TELEMETRY_DIR = BASE_DIR / "telemetry_output"
PLAYBOOKS_DIR = BASE_DIR / "driftless_playwright" / "playbooks"

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)

# LLM Configuration (Local Ollama default, easily overridden for Frontier Cloud)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5vl:7b")

# Embedding Configuration (nomic-embed-text 768-dim)
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Mock Sandbox Server Defaults
SANDBOX_HOST = os.getenv("SANDBOX_HOST", "127.0.0.1")
SANDBOX_PORT = int(os.getenv("SANDBOX_PORT", "8000"))
SANDBOX_URL = f"http://{SANDBOX_HOST}:{SANDBOX_PORT}"

# Hardware & Timeout Limits (tuned for 24 GB Mac)
DEFAULT_STEP_TIMEOUT_MS = int(os.getenv("DEFAULT_STEP_TIMEOUT_MS", "4000"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "5"))
MAX_ACTIONS_PER_STEP = 1
MAX_INPUT_TOKENS = 12000
TIER1_SIMILARITY_THRESHOLD = 0.82
