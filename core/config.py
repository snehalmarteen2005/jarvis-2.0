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
DB_PATH = Path(os.getenv("LIEBCHEN_DB_PATH", str(DATA_DIR / "liebchen.db")))
CHECKPOINT_DB_PATH = str(DATA_DIR / "checkpoints.db")

# ── Ollama LLM ─────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Qwen 2.5 3B recommended for 12GB RAM + HDD (2GB model vs 4.7GB for Llama 3 8B)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))

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
MAX_AGENT_ITERATIONS = int(os.getenv("LIEBCHEN_MAX_ITERATIONS", "4"))

# ── Voice ──────────────────────────────────────────────────────────────────────
VOICE_ENERGY_THRESHOLD = int(os.getenv("VOICE_ENERGY_THRESHOLD", "300"))
VOICE_PAUSE_THRESHOLD = float(os.getenv("VOICE_PAUSE_THRESHOLD", "1.5"))
