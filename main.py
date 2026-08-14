"""
Liebchen v2.0 — Main Entry Point

This replaces the old desktop.py with a clean, layered startup:

  Phase 1 (< 2s): Single-instance check → wake listener → tray → READY
  Phase 2 (on first wake): Lazy-load LLM, DB, graph in background
  Phase 3 (warm): All subsequent interactions use cached components

Optimized for: Ryzen 5 5625U · 12GB RAM · 1TB HDD
"""

from __future__ import annotations

import sys
import os
import threading
import time
import logging

# Fix for pythonw.exe (no stdout/stderr) and Windows cp1252 encoding
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
elif hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
elif hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

# ── Logging (lightweight, before anything else) ──────────────────────────────
import logging.handlers
from core.config import LOG_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "jarvis.log", maxBytes=5_000_000, backupCount=3
        ),
    ],
)
log = logging.getLogger("main")


# ── Phase 1: Enforce single instance (< 50ms) ───────────────────────────────
from core.singleton import enforce_single_instance, start_signal_listener
enforce_single_instance()
log.info("Single-instance lock acquired.")


# ── Imports (lightweight only — no LangChain, no Ollama) ─────────────────────
import winsound
import webview
import uvicorn
import speech_recognition as sr

from core.constants import (
    WAKE_WORDS, WAKE_COOLDOWN_SECONDS, WAKE_CONFIDENCE_MIN,
    AssistantState,
)
from core.config import OLLAMA_ENV, VOICE_ENERGY_THRESHOLD, VOICE_PAUSE_THRESHOLD
from core.lazy import LazyLoader
from ai.router import route
from services.conversation import ConversationManager


# ═══════════════════════════════════════════════════════════════════════════════
#  Global State
# ═══════════════════════════════════════════════════════════════════════════════

window = None
_last_activation = 0.0
conversation = ConversationManager(
    on_deactivate=lambda: _on_conversation_end()
)


def _on_conversation_end():
    """Called when conversation times out — keep window open as requested by user."""
    log.info("Conversation timed out — keeping window open.")
    # Do NOT hide the window — user wants window to stay open until manually closed or requested via voice


def _show_window():
    """Show and bring the window to front, with cooldown."""
    global _last_activation, window
    now = time.time()
    if now - _last_activation < WAKE_COOLDOWN_SECONDS:
        return
    _last_activation = now

    if window:
        try:
            window.show()
            window.restore()
            window.evaluate_js('if (typeof openPanel === "function") openPanel();')
        except Exception as e:
            log.warning(f"Could not show window: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Ollama Launcher
# ═══════════════════════════════════════════════════════════════════════════════

def start_ollama():
    """Ensure Ollama is running. Set performance env vars."""
    import urllib.request
    import subprocess

    # Set Ollama performance tuning env vars
    for key, value in OLLAMA_ENV.items():
        os.environ.setdefault(key, value)

    try:
        urllib.request.urlopen("http://127.0.0.1:11434/", timeout=1)
        log.info("Ollama already running.")
    except Exception:
        try:
            subprocess.Popen(
                "ollama serve", shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            log.info("Started Ollama server.")
            time.sleep(2)
        except Exception as e:
            log.warning(f"Could not start Ollama: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  FastAPI Server
# ═══════════════════════════════════════════════════════════════════════════════

def start_server():
    """Run the FastAPI server (lazy — imports server module on demand)."""
    try:
        from liebchen.api.server import app
        uvicorn.run(app, host="127.0.0.1", port=8888, log_level="error")
    except Exception as e:
        log.error(f"FastAPI server error: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  Background Voice Listener (Optimized)
# ═══════════════════════════════════════════════════════════════════════════════

def background_listener():
    """
    Persistent wake-word listener with continuous conversation support.

    Key optimizations over v1:
      - Mic stays open persistently (no per-loop hardware re-init)
      - Short calibration (0.5s vs 2s)
      - Conversation mode: after wake, commands don't need repeated wake word
      - Intent router: simple commands bypass LLM entirely
      - Lazy loading: heavy AI init happens in background on first wake
    """
    global window
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = VOICE_ENERGY_THRESHOLD
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = VOICE_PAUSE_THRESHOLD
    # Prevent premature cutoff mid-sentence, but ensure it obeys the assertion
    recognizer.non_speaking_duration = min(VOICE_PAUSE_THRESHOLD, 0.8)

    while True:
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)

                while True:
                    try:
                        phrase_limit = 25 if conversation.is_active else 3
                        timeout = 5 if conversation.is_active else 2
                        t0 = time.perf_counter()
                        audio = recognizer.listen(
                            source, timeout=timeout, phrase_time_limit=phrase_limit
                        )
                        t_listen = (time.perf_counter() - t0) * 1000
                    except sr.WaitTimeoutError:
                        continue

                    try:
                        t1 = time.perf_counter()
                        text = recognizer.recognize_google(audio).lower()
                        t_sr = (time.perf_counter() - t1) * 1000
                        log.info(f"[PROFILER] Speech Recognition: {t_sr:.2f} ms | Text: '{text}'")
                    except (sr.UnknownValueError, sr.RequestError):
                        continue

                    # ── Already in conversation mode ──
                    if conversation.is_active:
                        # Check for close/hide window command
                        if any(phrase in text for phrase in ("close window", "hide window", "close panel", "hide panel", "close jarvis", "hide jarvis")):
                            if window:
                                window.evaluate_js('if (typeof closePanel === "function") closePanel();')
                                window.hide()
                            continue

                        # Check for stop/shutdown
                        if "stop thinking" in text or "stop" in text or "cancel" in text:
                            if window:
                                window.evaluate_js(
                                    'if (typeof stopThinking === "function") stopThinking();'
                                )
                            _speak_via_ui("Stopped thinking. I'm listening.")
                            continue

                        if "shut down" in text or "go to sleep" in text:
                            _shutdown()
                            return

                        # If they say the wake word again while active → just acknowledge
                        if any(w in text for w in WAKE_WORDS):
                            _speak_via_ui("Jarvis is activated. I'm listening.")
                            continue

                        # Otherwise treat as a command
                        conversation.on_interaction()
                        _handle_command(text, source, recognizer)
                        continue

                    # ── Idle mode: check for wake word ──
                    if any(w in text for w in WAKE_WORDS):
                        log.info(f"[PROFILER] Wake Word Detected in {t_listen:.2f} ms")
                        _show_window()
                        conversation.activate()
                        _speak_via_ui("Jarvis is activated. I'm listening.")

                        # Kick off lazy loading in background (if not already done)
                        LazyLoader.start_background_init()
                        start_ollama()

                        # Listen for the follow-up command (extended 30s limit so user is not cut off)
                        try:
                            t0_cmd = time.perf_counter()
                            cmd_audio = recognizer.listen(
                                source, timeout=6, phrase_time_limit=30
                            )
                            t1_cmd = time.perf_counter()
                            cmd_text = recognizer.recognize_google(cmd_audio)
                            t_cmd_sr = (time.perf_counter() - t1_cmd) * 1000
                            log.info(f"[PROFILER] Command Speech Recognition: {t_cmd_sr:.2f} ms | Text: '{cmd_text}'")
                            
                            if cmd_text:
                                conversation.on_interaction()
                                _handle_command(cmd_text, source, recognizer)
                        except (sr.WaitTimeoutError, sr.UnknownValueError):
                            # User didn't say anything — that's fine
                            _speak_via_ui("I'm listening. What can I do?")

                    elif "shut down" in text or "go to sleep" in text:
                        _shutdown()
                        return

        except Exception as e:
            log.error(f"Listener error: {e}", exc_info=True)
            time.sleep(1)


def _handle_command(text: str, source, recognizer):
    """
    Route a voice command through the intent router.
    Fast-path commands execute instantly; complex ones go to LLM via UI.
    """
    t0 = time.perf_counter()
    result = route(text)
    t_route = (time.perf_counter() - t0) * 1000
    log.info(f"[PROFILER] Intent Router: {t_route:.2f} ms")

    if result.handled:
        # Fast-path: already executed, just show the response
        _speak_via_ui(result.response or "Done.")
    else:
        # LLM-path: inject text into the UI chat and let the API handle it
        if window and result.llm_input:
            safe_cmd = (
                result.llm_input
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("'", "\\'")
            )
            window.evaluate_js(f'''
                document.getElementById("msg-input").value = "{safe_cmd}";
                document.getElementById("btn-send").disabled = false;
                document.getElementById("btn-send").click();
            ''')


def _speak_via_ui(text: str):
    """Inject a quick response into the UI."""
    _show_window()
    if window:
        safe = text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
        window.evaluate_js(f'''
            if (typeof appendMessage === "function") {{
                appendMessage("{safe}", "ai");
            }}
            if (typeof speak === "function") {{
                speak("{safe}");
            }}
        ''')


def _shutdown():
    """Gracefully shut down the assistant."""
    global window
    winsound.PlaySound("SystemExit", winsound.SND_ALIAS | winsound.SND_ASYNC)
    log.info("Shutting down Jarvis...")
    if window:
        window.destroy()
    os._exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
#  Window Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

def on_closing():
    global window, _last_activation
    _last_activation = 0.0  # reset cooldown so immediate wake word works
    if window:
        try:
            window.evaluate_js('if (typeof closePanel === "function") closePanel();')
            window.hide()
        except Exception:
            pass
    return False


class Api:
    def quit(self):
        _shutdown()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    global window

    log.info("=" * 50)
    log.info("Liebchen v2.0 starting...")
    log.info("=" * 50)

    if not os.environ.get("OLLAMA_MODEL"):
        os.environ["OLLAMA_MODEL"] = "qwen2.5:3b"

    # Signal listener: duplicate launches bring this window to front
    start_signal_listener(_show_window)

    # FastAPI server (daemon thread)
    threading.Thread(target=start_server, daemon=True, name="api-server").start()

    # Voice listener (daemon thread)
    threading.Thread(target=background_listener, daemon=True, name="voice").start()

    # Wait for FastAPI server to bind port 8888 (max 5s)
    import socket
    for _ in range(50):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", 8888))
            s.close()
            break
        except Exception:
            time.sleep(0.1)

    # Create the window (hidden until wake word)
    window = webview.create_window(
        title="Jarvis Assistant",
        url="http://127.0.0.1:8888",
        width=1100,
        height=800,
        resizable=True,
        text_select=True,
        zoomable=True,
        hidden=True,
        js_api=Api(),
    )

    window.events.closing += on_closing
    log.info("Jarvis is ready. Listening for wake word...")
    webview.start()


if __name__ == "__main__":
    main()
