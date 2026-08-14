"""
Centralized constants and enums for the Liebchen assistant.
No heavy imports allowed — this module must load instantly.
"""

from enum import Enum

# ── Version ──────────────────────────────────────────────────────────────────
VERSION = "2.0.0"
APP_NAME = "Liebchen"
DISPLAY_NAME = "Jarvis Assistant"

# ── Single Instance ──────────────────────────────────────────────────────────
MUTEX_NAME = "LiebchenJarvisMutex"
LOCK_PORT = 49999
SIGNAL_PORT = 49998

# ── Wake Words ───────────────────────────────────────────────────────────────
WAKE_WORDS = frozenset({"jarvis", "liebchen", "hey jarvis", "assistant"})
WAKE_CONFIDENCE_MIN = 0.65
WAKE_COOLDOWN_SECONDS = 3.0

# ── Conversation ─────────────────────────────────────────────────────────────
CONVERSATION_TIMEOUT = 120  # seconds of silence before returning to idle (2 minutes)
MAX_CONTEXT_MESSAGES = 6   # sliding window size
MAX_TOOL_ITERATIONS = 2    # prevent infinite tool loops

# ── Performance ──────────────────────────────────────────────────────────────
OLLAMA_KEEP_ALIVE = "30m"
OLLAMA_NUM_THREADS = 4     # leave 2 cores for OS + app
MAX_TASK_WORKERS = 2       # ThreadPool size

# ── Security ─────────────────────────────────────────────────────────────────
COMMAND_TIMEOUT_SECONDS = 15


class AssistantState(str, Enum):
    """Global state machine for the assistant lifecycle."""
    IDLE = "idle"                  # listening for wake word only
    LISTENING = "listening"        # actively listening for a command
    THINKING = "thinking"          # LLM processing
    SPEAKING = "speaking"          # TTS output
    EXECUTING = "executing"        # running a tool/command
    CONVERSATION = "conversation"  # waiting for follow-up (15s timeout)
    ERROR = "error"                # recoverable error state


class IntentType(str, Enum):
    """Result of the intent router."""
    FAST_APP = "fast_app"          # open/close application
    FAST_SYSTEM = "fast_system"    # shutdown, restart, lock, etc.
    FAST_MEDIA = "fast_media"      # volume, brightness, screenshot
    FAST_INFO = "fast_info"        # time, date, battery
    FAST_SEARCH = "fast_search"    # web search (no LLM)
    LLM = "llm"                   # requires LangGraph + LLM
    CONVERSATION = "conversation"  # continuation of active conversation
    STOP = "stop"                  # stop/cancel current action
    SHUTDOWN = "shutdown"          # shut down the assistant
