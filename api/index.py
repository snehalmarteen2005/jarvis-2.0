import sys
from pathlib import Path

# Ensure the root project directory is on the path so Vercel can find the 'liebchen' package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from liebchen.api.server import app

# Vercel's Python runtime will look for the 'app' variable in this file
