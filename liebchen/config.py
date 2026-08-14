"""
Centralized configuration for the Liebchen agent.

All settings are loaded from environment variables with sensible defaults,
making it easy to override without touching code.
"""

import os
from pathlib import Path


# ── Project Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if os.getenv("VERCEL"):
    DATA_DIR = Path("/tmp")
else:
    DATA_DIR = PROJECT_ROOT / "data"

DATA_DIR.mkdir(exist_ok=True)

# ── Database ───────────────────────────────────────────────────────────────────
_db_env = os.getenv("LIEBCHEN_DB_PATH")
DB_PATH = Path(_db_env if _db_env else str(DATA_DIR / "liebchen.db"))

# ── Ollama LLM ─────────────────────────────────────────────────────────────────
_url_env = os.getenv("OLLAMA_BASE_URL")
OLLAMA_BASE_URL = _url_env if _url_env else "http://localhost:11434"

_model_env = os.getenv("OLLAMA_MODEL")
OLLAMA_MODEL = _model_env if _model_env else "llama3:8b"

_temp_env = os.getenv("OLLAMA_TEMPERATURE")
OLLAMA_TEMPERATURE = float(_temp_env if _temp_env else "0.7")

# ── Agent ──────────────────────────────────────────────────────────────────────
_iter_env = os.getenv("LIEBCHEN_MAX_ITERATIONS")
MAX_AGENT_ITERATIONS = int(_iter_env if _iter_env else "10")

# ── Checkpointer ───────────────────────────────────────────────────────────────
CHECKPOINT_DB_PATH = str(DATA_DIR / "checkpoints.db")
