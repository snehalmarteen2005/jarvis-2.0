"""
Intent Router — Two-tier command dispatcher.

Simple commands (open app, volume, screenshot) bypass the LLM entirely
and execute in < 50ms. Only complex requests that need reasoning go
through the full LangGraph → Ollama pipeline (2-8 seconds).

This is the SINGLE BIGGEST performance win in the v2.0 redesign.
"""

from __future__ import annotations

import re
import subprocess
import logging
from dataclasses import dataclass
from typing import Any, Callable

from core.constants import IntentType

log = logging.getLogger("ai.router")


@dataclass
class RouteResult:
    """Result of intent routing."""
    intent: IntentType
    response: str | None = None     # if already handled (fast-path)
    llm_input: str | None = None    # if needs LLM processing
    handled: bool = False           # True = already executed, no LLM needed


# ═══════════════════════════════════════════════════════════════════════════════
#  Fast-Path Executors
# ═══════════════════════════════════════════════════════════════════════════════

# Application name → executable mapping
APP_MAP = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "browser": "msedge.exe",
    "edge": "msedge.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "powershell": "powershell.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "paint": "mspaint.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "snipping tool": "snippingtool.exe",
}


def _execute_open_app(app_name: str) -> str:
    """Open an application without touching the LLM."""
    app_lower = app_name.lower().strip()
    command = APP_MAP.get(app_lower, app_lower)

    try:
        subprocess.Popen(f"start {command}", shell=True,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return f"✅ Opened {app_name}."
    except Exception as e:
        return f"❌ Couldn't open {app_name}: {e}"


def _execute_system(action: str) -> str:
    """Execute system commands directly."""
    commands = {
        "shutdown": ("shutdown /s /t 5", "💤 Shutting down in 5 seconds..."),
        "restart": ("shutdown /r /t 5", "🔄 Restarting in 5 seconds..."),
        "lock": ("rundll32.exe user32.dll,LockWorkStation", "🔒 Screen locked."),
        "sleep": ("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", "💤 Going to sleep..."),
        "logoff": ("shutdown /l", "👋 Logging off..."),
    }

    if action not in commands:
        return f"❌ Unknown system command: {action}"

    cmd, msg = commands[action]
    try:
        subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return msg
    except Exception as e:
        return f"❌ Failed: {e}"


def _execute_media(action: str) -> str:
    """Media/system control via PowerShell + SendKeys."""
    ps_commands = {
        "volume_up": (
            "powershell -Command \"(New-Object -ComObject WScript.Shell).SendKeys([char]175)\"",
            "🔊 Volume up."
        ),
        "volume_down": (
            "powershell -Command \"(New-Object -ComObject WScript.Shell).SendKeys([char]174)\"",
            "🔉 Volume down."
        ),
        "mute": (
            "powershell -Command \"(New-Object -ComObject WScript.Shell).SendKeys([char]173)\"",
            "🔇 Toggled mute."
        ),
        "screenshot": (
            "snippingtool",
            "📸 Screenshot tool opened."
        ),
    }

    if action not in ps_commands:
        return f"❌ Unknown media command: {action}"

    cmd, msg = ps_commands[action]
    try:
        subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return msg
    except Exception as e:
        return f"❌ Failed: {e}"


def _execute_info(query: str) -> str:
    """Quick info queries — no LLM needed."""
    from datetime import datetime
    if query == "time":
        return f"🕐 It's {datetime.now().strftime('%I:%M %p')}."
    elif query == "date":
        return f"📅 Today is {datetime.now().strftime('%A, %B %d, %Y')}."
    elif query == "battery":
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject Win32_Battery).EstimatedChargeRemaining"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            pct = result.stdout.strip()
            return f"🔋 Battery: {pct}%"
        except Exception:
            return "🔋 Couldn't read battery status."
    return f"❌ Unknown info query: {query}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Intent Pattern Matching
# ═══════════════════════════════════════════════════════════════════════════════

# Order matters: more specific patterns first
_INTENT_PATTERNS: list[tuple[str, Callable]] = [
    # ── System Control ──
    (r"^(?:please\s+)?shut\s*down(?:\s+(?:the\s+)?(?:pc|computer|laptop))?$",
     lambda m: RouteResult(IntentType.FAST_SYSTEM, _execute_system("shutdown"), handled=True)),
    (r"^(?:please\s+)?restart(?:\s+(?:the\s+)?(?:pc|computer|laptop))?$",
     lambda m: RouteResult(IntentType.FAST_SYSTEM, _execute_system("restart"), handled=True)),
    (r"^(?:please\s+)?lock(?:\s+(?:the\s+)?screen)?$",
     lambda m: RouteResult(IntentType.FAST_SYSTEM, _execute_system("lock"), handled=True)),
    (r"^(?:please\s+)?(?:go\s+to\s+)?sleep$",
     lambda m: RouteResult(IntentType.FAST_SYSTEM, _execute_system("sleep"), handled=True)),
    (r"^(?:please\s+)?log\s*off$",
     lambda m: RouteResult(IntentType.FAST_SYSTEM, _execute_system("logoff"), handled=True)),

    # ── App Launching ──
    (r"^(?:please\s+)?(?:open|launch|start|run)\s+(.+)$",
     lambda m: RouteResult(IntentType.FAST_APP, _execute_open_app(m.group(1)), handled=True)),
    (r"^(?:please\s+)?close\s+(.+)$",
     lambda m: RouteResult(IntentType.FAST_APP,
                           _close_app(m.group(1)), handled=True)),

    # ── Media Control ──
    (r"^volume\s+up$",
     lambda m: RouteResult(IntentType.FAST_MEDIA, _execute_media("volume_up"), handled=True)),
    (r"^volume\s+down$",
     lambda m: RouteResult(IntentType.FAST_MEDIA, _execute_media("volume_down"), handled=True)),
    (r"^(?:toggle\s+)?mute$",
     lambda m: RouteResult(IntentType.FAST_MEDIA, _execute_media("mute"), handled=True)),
    (r"^(?:take\s+(?:a\s+)?)?screenshot$",
     lambda m: RouteResult(IntentType.FAST_MEDIA, _execute_media("screenshot"), handled=True)),

    # ── Quick Info ──
    (r"^what(?:'s|\s+is)\s+(?:the\s+)?time$",
     lambda m: RouteResult(IntentType.FAST_INFO, _execute_info("time"), handled=True)),
    (r"^what(?:'s|\s+is)\s+(?:the\s+)?(?:today'?s?\s+)?date$",
     lambda m: RouteResult(IntentType.FAST_INFO, _execute_info("date"), handled=True)),
    (r"^(?:check\s+)?battery(?:\s+(?:level|status))?$",
     lambda m: RouteResult(IntentType.FAST_INFO, _execute_info("battery"), handled=True)),

    # ── Web Search (fast — uses DuckDuckGo directly, no LLM) ──
    (r"^(?:search|google|look\s+up|find)\s+(?:for\s+)?(.+)$",
     lambda m: RouteResult(IntentType.FAST_SEARCH, _execute_search(m.group(1)), handled=True)),

    # ── Stop / Cancel ──
    (r"^(?:stop\s+thinking|stop\s+processing|stop|cancel|never\s*mind|abort)$",
     lambda m: RouteResult(IntentType.STOP, "⏹️ Stopped thinking. I'm listening.", handled=True)),
]


def _close_app(app_name: str) -> str:
    """Kill a running application by name."""
    try:
        subprocess.run(
            ["taskkill", "/IM", f"{app_name.strip()}.exe", "/F"],
            capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return f"✅ Closed {app_name}."
    except Exception as e:
        return f"❌ Couldn't close {app_name}: {e}"


def _execute_search(query: str) -> str:
    """Direct web search without LLM — returns top 3 results."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return f"❌ No results for '{query}'."
        lines = [f"🔍 Results for '{query}':\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title')}**\n   {r.get('body')}")
        return "\n\n".join(lines)
    except ImportError:
        return "❌ Search not available (duckduckgo-search not installed)."
    except Exception as e:
        return f"❌ Search failed: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Router
# ═══════════════════════════════════════════════════════════════════════════════

def route(text: str) -> RouteResult:
    """
    Route user input to the appropriate handler.

    Returns a RouteResult. If result.handled is True, the response
    is already in result.response — no LLM call needed.
    If result.handled is False, send result.llm_input to LangGraph.
    """
    text_clean = text.strip()
    text_lower = text_clean.lower()

    # ── OPTIMIZATION: Strip Wake Words ──
    # If the user says "Jarvis open chrome" while already active, remove "jarvis"
    # so the fast-path regex can match "^open chrome$".
    from core.constants import WAKE_WORDS
    for w in WAKE_WORDS:
        if text_lower.startswith(w + " "):
            text_lower = text_lower[len(w)+1:].strip()
            text_clean = text_clean[len(w)+1:].strip()
            break
        elif text_lower == w:
            text_lower = ""
            text_clean = ""
            break

    # Try fast-path patterns
    for pattern, handler in _INTENT_PATTERNS:
        match = re.match(pattern, text_lower)
        if match:
            log.info(f"Fast-path match: '{text_lower}' → {pattern}")
            return handler(match)

    # No fast-path match — route to LLM
    log.info(f"LLM-path: '{text_lower[:50]}...'")
    return RouteResult(
        intent=IntentType.LLM,
        llm_input=text_clean,
        handled=False,
    )
