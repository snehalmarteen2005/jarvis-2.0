"""
Centralized configuration loaded from environment variables.

Replaces liebchen/config.py with HDD-optimized defaults
and Ollama tuning for Ryzen 5 5625U + 12GB RAM.
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
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Database ───────────────────────────────────────────────────────────────────
_db_env = os.getenv("LIEBCHEN_DB_PATH")
DB_PATH = Path(_db_env if _db_env else str(DATA_DIR / "liebchen.db"))
CHECKPOINT_DB_PATH = str(DATA_DIR / "checkpoints.db")

# ── Ollama LLM ─────────────────────────────────────────────────────────────────
_url_env = os.getenv("OLLAMA_BASE_URL")
OLLAMA_BASE_URL = _url_env if _url_env else "http://localhost:11434"

_model_env = os.getenv("OLLAMA_MODEL")
OLLAMA_MODEL = _model_env if _model_env else "qwen2.5:3b"

_temp_env = os.getenv("OLLAMA_TEMPERATURE")
OLLAMA_TEMPERATURE = float(_temp_env if _temp_env else "0.7")

# ── Ollama Performance Tuning ─────────────────────────────────────────────────
# These are set as env vars BEFORE Ollama starts
OLLAMA_ENV = {
    "OLLAMA_NUM_PARALLEL": "1",       # single request at a time (save RAM)
    "OLLAMA_MAX_LOADED_MODELS": "1",  # only one model in memory
    "OLLAMA_KEEP_ALIVE": "24h",       # keep model loaded for 24h (HUGE HDD optimization)
    "OLLAMA_NUM_GPU": "0",            # no discrete GPU, CPU only
    "OLLAMA_NUM_THREAD": "8",         # Use 8 of 12 threads for faster inference on Ryzen 5
}

# ── Agent ──────────────────────────────────────────────────────────────────────
_iter_env = os.getenv("LIEBCHEN_MAX_ITERATIONS")
MAX_AGENT_ITERATIONS = int(_iter_env if _iter_env else "4")

# ── Voice ──────────────────────────────────────────────────────────────────────
_eng_env = os.getenv("VOICE_ENERGY_THRESHOLD")
VOICE_ENERGY_THRESHOLD = int(_eng_env if _eng_env else "300")

_pause_env = os.getenv("VOICE_PAUSE_THRESHOLD")
VOICE_PAUSE_THRESHOLD = float(_pause_env if _pause_env else "1.5")
