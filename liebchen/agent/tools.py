"""
Core tools for the Liebchen agent.

Each tool is a Python function decorated with @tool. LangGraph's ToolNode
will automatically execute these when the LLM decides to call them.

Tools interact with the SQLite database via the CRUD helpers in
liebchen.database.models.
"""

from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from typing import Optional

from langchain_core.tools import tool

from liebchen.database import models


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 1: Analyze Skills
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def analyze_skills(
    user_id: int = 1,
    new_skills: Optional[str] = None,
    bio: Optional[str] = None,
) -> str:
    """
    Analyze a user's current skills against their goals to identify skill gaps.

    Use this tool when:
    - A user shares their background or current skills
    - A user asks "what should I learn?"
    - You need to create or update a learning plan

    Args:
        user_id: The user's database ID (default 1 for single-user mode).
        new_skills: Comma-separated list of new skills to record,
                    e.g. "Python:intermediate,SQL:beginner,Git:advanced"
        bio: Updated bio/background text to save for the user.

    Returns:
        A formatted analysis including current skills, goals, and identified gaps.
    """
    # If new skills were provided, save them
    if new_skills:
        for entry in new_skills.split(","):
            entry = entry.strip()
            if ":" in entry:
                skill_name, proficiency = entry.rsplit(":", 1)
                models.add_skill(user_id, skill_name.strip(), proficiency.strip())
            else:
                models.add_skill(user_id, entry.strip())

    # If bio was provided, update the user
    if bio:
        user = models.get_user(user_id)
        if user:
            models.upsert_user(
                name=user["name"], bio=bio,
                current_level=user["current_level"],
                preferred_hours=user["preferred_hours"],
                user_id=user_id,
            )

    # Gather current data
    user = models.get_user(user_id)
    skills = models.get_skills(user_id)
    goals = models.get_goals(user_id)

    # Build the analysis report
    report_parts = []

    report_parts.append("## 📊 Skill Analysis Report\n")

    if user:
        report_parts.append(f"**User:** {user['name']}")
        report_parts.append(f"**Level:** {user['current_level']}")
        if user.get("bio"):
            report_parts.append(f"**Bio:** {user['bio']}")
        report_parts.append("")

    if skills:
        report_parts.append("### Current Skills")
        for s in skills:
            report_parts.append(f"- **{s['skill_name']}** — {s['proficiency_level']} ({s['category']})")
        report_parts.append("")
    else:
        report_parts.append("### Current Skills\n_No skills recorded yet. Tell me about your background!_\n")

    if goals:
        report_parts.append("### Active Goals")
        for g in goals:
            line = f"- **{g['goal_title']}** [{g['priority']}]"
            if g.get("target_role"):
                line += f" → Target: {g['target_role']}"
            if g.get("target_date"):
                line += f" (by {g['target_date']})"
            report_parts.append(line)
        report_parts.append("")
    else:
        report_parts.append("### Goals\n_No goals set yet. What do you want to achieve?_\n")

    report_parts.append("### 🧩 Analysis")
    report_parts.append(
        "Based on the skills and goals above, I can identify gaps and create "
        "a tailored learning plan. Ask me to generate a plan!"
    )

    return "\n".join(report_parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 2: Update Timetable
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def update_timetable(
    action: str,
    user_id: int = 1,
    topic: Optional[str] = None,
    scheduled_date: Optional[str] = None,
    start_time: str = "09:00",
    end_time: str = "10:00",
    description: str = "",
    estimated_minutes: int = 60,
    entry_id: Optional[int] = None,
    new_status: Optional[str] = None,
    new_date: Optional[str] = None,
) -> str:
    """
    Create, modify, or query timetable entries for the user's study schedule.

    Use this tool when:
    - Creating a new study schedule
    - Rescheduling a missed session
    - Marking a session as completed
    - Viewing the current schedule

    Args:
        action: One of 'add', 'update', 'reschedule', 'view', 'view_today'.
        user_id: The user's database ID.
        topic: Topic/subject for the study session (required for 'add').
        scheduled_date: ISO date string YYYY-MM-DD (required for 'add').
        start_time: Start time HH:MM (default 09:00).
        end_time: End time HH:MM (default 10:00).
        description: Optional description of what to study.
        estimated_minutes: Expected duration in minutes.
        entry_id: Timetable entry ID (required for 'update' and 'reschedule').
        new_status: New status for 'update' action (pending/completed/skipped).
        new_date: New date for 'reschedule' action.

    Returns:
        A formatted string confirming the action or showing the timetable.
    """
    if action == "add":
        if not topic or not scheduled_date:
            return "❌ Error: 'topic' and 'scheduled_date' are required to add an entry."
        entry = models.add_timetable_entry(
            user_id=user_id,
            topic=topic,
            scheduled_date=scheduled_date,
            start_time=start_time,
            end_time=end_time,
            description=description,
            estimated_minutes=estimated_minutes,
        )
        return (
            f"✅ Added to timetable:\n"
            f"- **{entry['topic']}** on {entry['scheduled_date']}\n"
            f"- Time: {entry['start_time']} – {entry['end_time']} ({entry['estimated_minutes']} min)"
        )

    elif action == "update":
        if not entry_id:
            return "❌ Error: 'entry_id' is required for update."
        updates = {}
        if new_status:
            updates["status"] = new_status
        if topic:
            updates["topic"] = topic
        if description:
            updates["description"] = description
        result = models.update_timetable_entry(entry_id, **updates)
        if result:
            return f"✅ Updated entry #{entry_id}: status → {result.get('status', 'unchanged')}"
        return f"❌ Entry #{entry_id} not found."

    elif action == "reschedule":
        if not entry_id or not new_date:
            return "❌ Error: 'entry_id' and 'new_date' are required to reschedule."
        result = models.update_timetable_entry(entry_id, scheduled_date=new_date, status="rescheduled")
        if result:
            return f"📅 Rescheduled entry #{entry_id} → {new_date}"
        return f"❌ Entry #{entry_id} not found."

    elif action == "view_today":
        today = date.today().isoformat()
        entries = models.get_timetable(user_id, date_str=today)
        if not entries:
            return "📅 No sessions scheduled for today."
        lines = ["## 📅 Today's Schedule\n"]
        for e in entries:
            status_icon = {"pending": "⏳", "completed": "✅", "in_progress": "🔄", "skipped": "⏭️"}.get(e["status"], "📌")
            lines.append(f"{status_icon} **{e['start_time']}–{e['end_time']}** | {e['topic']} [{e['status']}]")
        return "\n".join(lines)

    elif action == "view":
        entries = models.get_timetable(user_id)
        if not entries:
            return "📅 No upcoming sessions in the timetable."
        lines = ["## 📅 Upcoming Schedule\n"]
        current_date = ""
        for e in entries:
            if e["scheduled_date"] != current_date:
                current_date = e["scheduled_date"]
                lines.append(f"\n### {current_date}")
            status_icon = {"pending": "⏳", "completed": "✅", "in_progress": "🔄", "skipped": "⏭️"}.get(e["status"], "📌")
            lines.append(f"{status_icon} **{e['start_time']}–{e['end_time']}** | {e['topic']} (#{e['id']})")
        return "\n".join(lines)

    return f"❌ Unknown action: '{action}'. Use: add, update, reschedule, view, view_today."


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 3: Explain Topic
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def explain_topic(
    topic: str,
    depth: str = "intermediate",
    user_id: int = 1,
) -> str:
    """
    Provide context for the LLM to give a clear, structured explanation of an educational topic.

    Use this tool when:
    - The user asks "explain X" or "teach me about Y"
    - The user is working through a timetable entry and needs clarification

    Args:
        topic: The topic or concept to explain.
        depth: Detail level — 'beginner', 'intermediate', or 'advanced'.
        user_id: The user's database ID (to check their level).

    Returns:
        A prompt context string that helps the LLM generate a high-quality explanation.
    """
    user = models.get_user(user_id)
    user_level = user["current_level"] if user else "beginner"

    # Check if this topic relates to any of their skills
    skills = models.get_skills(user_id)
    related_skills = [s for s in skills if s["skill_name"].lower() in topic.lower() or topic.lower() in s["skill_name"].lower()]

    context_parts = [
        f"## 📖 Topic Explanation Request",
        f"**Topic:** {topic}",
        f"**Requested Depth:** {depth}",
        f"**User Level:** {user_level}",
    ]

    if related_skills:
        context_parts.append(f"**Related Skills:** {', '.join(s['skill_name'] + ' (' + s['proficiency_level'] + ')' for s in related_skills)}")

    context_parts.extend([
        "",
        "Please provide a clear, structured explanation that includes:",
        "1. **What it is** — A concise definition",
        "2. **Why it matters** — Real-world relevance",
        "3. **How it works** — Core mechanics/concepts",
        "4. **Example** — A concrete, practical example",
        "5. **Key takeaways** — 3-5 bullet points to remember",
        "",
        f"Adjust the complexity for a **{depth}** audience.",
    ])

    return "\n".join(context_parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 4: Get Pending Tasks
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def get_pending_tasks(user_id: int = 1) -> str:
    """
    Retrieve the user's pending and overdue timetable tasks.

    Use this tool when:
    - Greeting a returning user
    - The user asks "what should I do today?"
    - Checking for overdue items to trigger rescheduling

    Args:
        user_id: The user's database ID.

    Returns:
        A formatted summary of pending tasks, separated into today, upcoming, and overdue.
    """
    today = date.today().isoformat()
    all_entries = models.get_timetable(user_id)
    progress = models.get_progress_summary(user_id)

    overdue = []
    today_tasks = []
    upcoming = []

    for e in all_entries:
        if e["status"] in ("completed", "skipped", "rescheduled"):
            continue
        if e["scheduled_date"] < today:
            overdue.append(e)
        elif e["scheduled_date"] == today:
            today_tasks.append(e)
        else:
            upcoming.append(e)

    lines = ["## 📋 Task Summary\n"]

    # Progress overview
    lines.append(f"**Overall Progress:** {progress['completed']}/{progress['total_entries']} tasks completed "
                 f"({progress['completion_rate_pct']}%)\n")

    # Overdue
    if overdue:
        lines.append(f"### 🔴 Overdue ({len(overdue)} tasks)")
        for e in overdue:
            lines.append(f"- ⚠️ **{e['topic']}** — was due {e['scheduled_date']} (#{e['id']})")
        lines.append("")

    # Today
    if today_tasks:
        lines.append(f"### 🟡 Today ({len(today_tasks)} tasks)")
        for e in today_tasks:
            lines.append(f"- ⏳ **{e['start_time']}–{e['end_time']}** | {e['topic']} (#{e['id']})")
        lines.append("")
    else:
        lines.append("### 🟢 Today\n_No tasks scheduled for today._\n")

    # Upcoming (next 7 days max)
    week_later = (date.today() + timedelta(days=7)).isoformat()
    near_upcoming = [e for e in upcoming if e["scheduled_date"] <= week_later]
    if near_upcoming:
        lines.append(f"### 🔵 Upcoming This Week ({len(near_upcoming)} tasks)")
        for e in near_upcoming[:10]:  # Cap at 10
            lines.append(f"- 📌 {e['scheduled_date']} | **{e['topic']}** {e['start_time']}–{e['end_time']}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 5: Log Progress
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def log_progress_tool(
    user_id: int = 1,
    entry_id: Optional[int] = None,
    notes: str = "",
    completion_pct: float = 100.0,
    difficulty: str = "medium",
    mark_complete: bool = True,
) -> str:
    """
    Record the user's progress on a timetable task.

    Use this tool when:
    - The user says they finished studying a topic
    - The user gives feedback about difficulty
    - You need to update completion status

    Args:
        user_id: The user's database ID.
        entry_id: The timetable entry ID being tracked (optional).
        notes: User's notes or feedback about the session.
        completion_pct: Percentage completed (0-100).
        difficulty: How hard it was — easy, medium, hard, very_hard.
        mark_complete: If True and completion_pct is 100, also mark the
                       timetable entry as 'completed'.

    Returns:
        Confirmation of the logged progress.
    """
    log = models.log_progress(
        user_id=user_id,
        entry_id=entry_id,
        notes=notes,
        completion_pct=completion_pct,
        difficulty_rating=difficulty,
    )

    # Also mark the timetable entry as completed if applicable
    if mark_complete and entry_id and completion_pct >= 100:
        models.update_timetable_entry(entry_id, status="completed")

    lines = [
        "✅ Progress logged!",
        f"- **Completion:** {completion_pct}%",
        f"- **Difficulty:** {difficulty}",
    ]
    if notes:
        lines.append(f"- **Notes:** {notes}")
    if mark_complete and entry_id and completion_pct >= 100:
        lines.append(f"- 🎉 Task #{entry_id} marked as **completed**!")

    # Get updated summary
    summary = models.get_progress_summary(user_id)
    lines.append(f"\n📊 **Overall:** {summary['completed']}/{summary['total_entries']} tasks done ({summary['completion_rate_pct']}%)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 6: Open Application
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def open_application(app_name: str) -> str:
    """
    Open an application on the user's PC using a voice command.
    
    Use this tool when:
    - The user says "open [application]" or "start [application]"
    
    Args:
        app_name: The name of the application to open (e.g., "notepad", "calculator", "chrome").
        
    Returns:
        Confirmation of the action or an error message.
    """
    import os
    import subprocess
    
    app_name_lower = app_name.lower().strip()
    
    # Common app mappings for Windows
    common_apps = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "chrome": "chrome.exe",
        "browser": "msedge.exe",
        "edge": "msedge.exe",
        "explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "terminal": "wt.exe",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
        "paint": "mspaint.exe",
    }
    
    command = common_apps.get(app_name_lower, app_name_lower)
    
    try:
        subprocess.Popen(f"start {command}", shell=True)
        return f"✅ Opened application: {app_name}"
    except Exception as e:
        return f"❌ Failed to open {app_name}. Error: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 7: Search Web
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def search_web(query: str) -> str:
    """
    Search the web for information using DuckDuckGo.
    
    Use this tool when:
    - The user asks a general knowledge question (e.g., "what is api")
    - You need to look up current information or facts you don't know
    
    Args:
        query: The search query.
        
    Returns:
        Search results summarized.
    """
    try:
        from duckduckgo_search import DDGS
        # Add 10s timeout to prevent hanging the entire agent pipeline
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.text(query, max_results=3))
            
        if not results:
            return f"❌ No results found for '{query}'."
            
        report = [f"🔍 Search results for '{query}':\n"]
        for i, res in enumerate(results, 1):
            report.append(f"{i}. **{res.get('title')}**\n   {res.get('body')}\n   [Link]({res.get('href')})")
            
        return "\n\n".join(report)
    except ImportError:
        return "❌ Search tool is not available (duckduckgo-search package not installed)."
    except Exception as e:
        return f"❌ Search failed: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 8: Run Terminal Command
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def run_terminal_command(command: str) -> str:
    """
    Run an arbitrary command in the Windows command prompt/PowerShell.
    Use this to access the whole PC, launch applications not in the common list, open files, or execute scripts.
    WARNING: Has full access to the user's PC.
    
    Args:
        command: The shell command to run.
        
    Returns:
        The output of the command or an error message.
    """
    import subprocess
    try:
        # Using powershell as the shell to give it more capabilities
        result = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True, timeout=15)
        out = result.stdout.strip()
        err = result.stderr.strip()
        
        response = []
        if out:
            response.append(f"Output:\n{out}")
        if err:
            response.append(f"Errors:\n{err}")
            
        if not response:
            return "✅ Command executed successfully (no output)."
        return "\n\n".join(response)
    except subprocess.TimeoutExpired:
        return "❌ Command timed out after 15 seconds."
    except Exception as e:
        return f"❌ Failed to execute command: {str(e)}"


# ── Tool Registry ─────────────────────────────────────────────────────────────

ALL_TOOLS = [
    analyze_skills,
    update_timetable,
    explain_topic,
    get_pending_tasks,
    log_progress_tool,
    open_application,
    search_web,
    run_terminal_command,
]

