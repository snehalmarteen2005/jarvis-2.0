"""
Liebchen Web API — FastAPI backend for the voice-activated UI.

Provides:
  - /api/chat  — Send a message to the agent, get a response
  - /api/health — Server + Ollama health check
  - /           — Serves the web UI
"""

from __future__ import annotations

import os
import sys
import uuid
import sqlite3
import json
import logging
import traceback
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from liebchen.database.models import initialize_database, get_user
from liebchen.llm.ollama_client import get_llm, check_ollama_health
from liebchen.agent.graph import build_graph

from langchain_core.messages import HumanMessage

log = logging.getLogger("api.server")

# ── Environment Detection ────────────────────────────────────────────────────
IS_VERCEL = bool(os.getenv("VERCEL"))

# ── Global state ──────────────────────────────────────────────────────────────
_graph = None
_config = None
_user_id = 1
_initialized = False


def _lazy_init():
    """
    Lazy initialization for serverless environments.
    On Vercel, there is no persistent background thread — we initialize on first request.
    """
    global _graph, _config, _user_id, _initialized

    if _initialized:
        return

    try:
        # Initialize database
        initialize_database()
        log.info("[API] Database initialized")

        # Check user
        user = get_user(1)
        if user:
            log.info(f"[API] User: {user['name']}")
            _user_id = user["id"]
    except Exception as e:
        log.warning(f"[API] Database init warning: {e}")

    # Build the agent graph (uses Groq on cloud, Ollama locally)
    try:
        llm = get_llm()
        _graph, _ = build_graph(llm=llm)
        log.info("[API] Agent graph ready")
    except Exception as e:
        log.error(f"[API] Failed to build graph: {e}")
        log.error(traceback.format_exc())

    # Create a default thread ID
    thread_id = f"web-{uuid.uuid4().hex[:8]}"
    _config = {"configurable": {"thread_id": thread_id}}

    _initialized = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup (for non-serverless environments)."""
    if not IS_VERCEL:
        print("[API] Liebchen Web API starting...")
        _lazy_init()
        print(f"[API] Web API ready")

    yield

    print("[API] Liebchen Web API shutting down...")


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Liebchen AI",
    description="Voice-activated AI Learning Companion",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ───────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    thread_id: str


# ── Intent Router (safe import) ──────────────────────────────────────────────
def _safe_route(text: str):
    """Try to use the intent router, but don't crash if it fails on Linux."""
    try:
        from ai.router import route
        return route(text)
    except Exception:
        return None


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Check server and Ollama health."""
    _lazy_init()
    ollama = check_ollama_health()
    user = get_user(_user_id)

    # Import config safely
    try:
        from liebchen.config import OLLAMA_MODEL
        model = OLLAMA_MODEL
    except Exception:
        model = "groq-cloud" if os.getenv("GROQ_API_KEY") else "unknown"

    return {
        "status": "ok",
        "ollama": ollama,
        "user": user["name"] if user else None,
        "model": model,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to the Liebchen agent."""
    _lazy_init()

    thread_id = req.thread_id or (_config["configurable"]["thread_id"] if _config else f"web-{uuid.uuid4().hex[:8]}")
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Fast-Path Intent Router Check (< 50ms bypass)
    route_res = _safe_route(req.message)
    if route_res and route_res.handled and route_res.response:
        return ChatResponse(
            response=route_res.response,
            thread_id=thread_id,
        )

    # 2. LLM-path
    if not _graph:
        raise HTTPException(status_code=503, detail="Agent failed to initialize. Check server logs.")

    try:
        result = _graph.invoke(
            {"messages": [HumanMessage(content=req.message)], "user_id": _user_id},
            config=config,
        )

        ai_msg = result["messages"][-1]
        return ChatResponse(
            response=ai_msg.content,
            thread_id=thread_id,
        )
    except Exception as e:
        log.error(f"Chat error: {e}")
        log.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat_stream")
async def chat_stream(req: ChatRequest):
    """Stream messages from the Liebchen agent."""
    _lazy_init()

    thread_id = req.thread_id or (_config["configurable"]["thread_id"] if _config else f"web-{uuid.uuid4().hex[:8]}")
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Fast-Path Intent Router Check
    route_res = _safe_route(req.message)
    if route_res and route_res.handled and route_res.response:
        async def fast_stream():
            yield f"data: {json.dumps({'chunk': route_res.response, 'thread_id': thread_id})}\n\n"
        return StreamingResponse(fast_stream(), media_type="text/event-stream")

    if not _graph:
        raise HTTPException(status_code=503, detail="Agent failed to initialize. Check server logs.")

    async def event_stream():
        try:
            # We use astream_events to get tokens from the LLM in real-time
            async for event in _graph.astream_events(
                {"messages": [HumanMessage(content=req.message)], "user_id": _user_id},
                config=config,
                version="v2"
            ):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    content = ""
                    if isinstance(chunk, str):
                        content = chunk
                    elif isinstance(chunk, dict) and "content" in chunk:
                        content = chunk["content"]
                    elif hasattr(chunk, "content"):
                        content = chunk.content

                    if content:
                        # Yield Server-Sent Event
                        yield f"data: {json.dumps({'chunk': content, 'thread_id': thread_id})}\n\n"
        except Exception as e:
            log.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/new-thread")
async def new_thread():
    """Create a new conversation thread."""
    global _config
    thread_id = f"web-{uuid.uuid4().hex[:8]}"
    _config = {"configurable": {"thread_id": thread_id}}
    return {"thread_id": thread_id}


# ── Serve Static UI ──────────────────────────────────────────────────────────
UI_DIR = Path(__file__).resolve().parent.parent.parent / "web"

@app.get("/")
async def serve_ui():
    """Serve the main UI."""
    index = UI_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"error": "UI not found. Run from project root."}, status_code=404)


# Mount static files after routes
@app.get("/styles.css")
async def serve_css():
    return FileResponse(UI_DIR / "styles.css", media_type="text/css")

@app.get("/app.js")
async def serve_js():
    return FileResponse(UI_DIR / "app.js", media_type="application/javascript")
