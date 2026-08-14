"""
System startup greeter.

This module handles the greeting logic that runs when the agent
starts up (either via system boot or manual launch).
"""

from __future__ import annotations

from datetime import datetime

from langchain_core.messages import HumanMessage

from liebchen.database.models import get_user, get_timetable, get_progress_summary


def get_greeting_context(user_id: int = 1) -> str:
    """
    Build a context-rich greeting prompt for the agent.

    Gathers the user's profile, today's schedule, and progress stats
    to create a personalized morning briefing.
    """
    now = datetime.now()
    hour = now.hour

    # Time-appropriate greeting
    if hour < 12:
        time_greeting = "Good morning"
    elif hour < 17:
        time_greeting = "Good afternoon"
    else:
        time_greeting = "Good evening"

    user = get_user(user_id)
    name = user["name"] if user else "there"

    # Get today's tasks
    today_str = now.strftime("%Y-%m-%d")
    today_tasks = get_timetable(user_id, date_str=today_str)

    # Get overall progress
    try:
        progress = get_progress_summary(user_id)
    except Exception:
        progress = None

    # Build the greeting message
    parts = [f"{time_greeting}, {name}! 👋"]
    parts.append(f"It's {now.strftime('%A, %B %d, %Y')} at {now.strftime('%I:%M %p')}.")

    if today_tasks:
        pending = [t for t in today_tasks if t["status"] == "pending"]
        completed = [t for t in today_tasks if t["status"] == "completed"]
        parts.append(f"\n📅 **Today's Schedule:** {len(today_tasks)} sessions planned")
        if completed:
            parts.append(f"   ✅ {len(completed)} already completed")
        if pending:
            parts.append(f"   ⏳ {len(pending)} still pending:")
            for t in pending:
                parts.append(f"      • {t['start_time']}–{t['end_time']}: {t['topic']}")
    else:
        parts.append("\n📅 No sessions scheduled for today.")

    if progress and progress["total_entries"] > 0:
        parts.append(f"\n📊 **Overall Progress:** {progress['completion_rate_pct']}% complete")

    parts.append("\nWhat would you like to work on?")

    return "\n".join(parts)


def create_startup_message(user_id: int = 1) -> HumanMessage:
    """
    Create the initial HumanMessage that triggers the agent's greeting.

    This is used when the agent starts up on system boot.
    """
    context = get_greeting_context(user_id)
    return HumanMessage(
        content=f"[SYSTEM STARTUP] Please greet me and summarize my day.\n\nContext:\n{context}"
    )
