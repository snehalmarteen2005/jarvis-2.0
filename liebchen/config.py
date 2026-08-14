"""
Centralized configuration for the Liebchen agent.

All settings are loaded from environment variables with sensible defaults,
making it easy to override without touching code.
"""

import os
from pathlib import Path


# ── Project Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Database ───────────────────────────────────────────────────────────────────
DB_PATH = Path(os.getenv("LIEBCHEN_DB_PATH", str(DATA_DIR / "liebchen.db")))

# ── Ollama LLM ─────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))

# ── Agent ──────────────────────────────────────────────────────────────────────
MAX_AGENT_ITERATIONS = int(os.getenv("LIEBCHEN_MAX_ITERATIONS", "10"))

# ── Checkpointer ───────────────────────────────────────────────────────────────
CHECKPOINT_DB_PATH = str(DATA_DIR / "checkpoints.db")
