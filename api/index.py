"""
Vercel Serverless entry point for Liebchen API.

This is a thin wrapper that Vercel's @vercel/python runtime discovers.
It imports the FastAPI `app` so Vercel can serve it as a serverless function.
"""

import os
import sys
from pathlib import Path

# Ensure the root project directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Force VERCEL flag (Vercel sets this automatically, but be safe) ──
os.environ.setdefault("VERCEL", "1")

from liebchen.api.server import app  # noqa: E402, F401

# Vercel's Python runtime will look for the 'app' variable in this file
