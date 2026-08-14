#!/usr/bin/env python3
"""
Liebchen CLI — Interactive terminal interface for the AI agent.

This is the primary entry point during development (Phase 1).
It provides an interactive REPL where you can chat with the agent,
and special commands for common operations.

Usage:
    python cli.py
    python cli.py --startup    # Trigger startup greeting
    python cli.py --setup      # Run first-time setup wizard
"""

from __future__ import annotations

import argparse
import sys
import uuid

from langchain_core.messages import HumanMessage, AIMessage

from liebchen.database.models import initialize_database, upsert_user, get_user, add_goal
from liebchen.llm.ollama_client import get_llm_with_health_check
from liebchen.agent.graph import build_graph
from liebchen.startup.greeter import create_startup_message


# ── ANSI Colors ────────────────────────────────────────────────────────────────
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


BANNER = f"""
{CYAN}{BOLD}
 ╔══════════════════════════════════════════════════════╗
 ║              🧠  L I E B C H E N                    ║
 ║     Your Local AI Learning Companion & Coach         ║
 ╚══════════════════════════════════════════════════════╝
{RESET}
{DIM} Type your message to chat with the agent.
 Special commands:
   /help      — Show all commands
   /setup     — Run first-time setup
   /tasks     — Show pending tasks
   /schedule  — View your timetable
   /progress  — View progress summary
   /quit      — Exit the application
{RESET}
"""

HELP_TEXT = f"""
{YELLOW}{BOLD}Available Commands:{RESET}
  {GREEN}/help{RESET}      — Show this help message
  {GREEN}/setup{RESET}     — Run the interactive setup wizard
  {GREEN}/tasks{RESET}     — Ask the agent about your pending tasks
  {GREEN}/schedule{RESET}  — Ask the agent to show your timetable
  {GREEN}/progress{RESET}  — Ask the agent about your progress
  {GREEN}/startup{RESET}   — Trigger the startup greeting
  {GREEN}/clear{RESET}     — Start a new conversation thread
  {GREEN}/quit{RESET}      — Exit Liebchen

{DIM}Or just type naturally — Liebchen understands free-form questions!{RESET}
"""


def run_setup_wizard() -> int:
    """Interactive first-time setup. Returns the user_id."""
    print(f"\n{CYAN}{BOLD}═══ First-Time Setup ═══{RESET}\n")

    name = input(f"{GREEN}Your name: {RESET}").strip() or "User"
    bio = input(f"{GREEN}Brief bio (background, experience): {RESET}").strip()

    level_map = {"1": "beginner", "2": "intermediate", "3": "advanced"}
    print(f"\n{GREEN}Your current level:{RESET}")
    print("  1) Beginner")
    print("  2) Intermediate")
    print("  3) Advanced")
    level_choice = input(f"{GREEN}Choose (1-3): {RESET}").strip()
    level = level_map.get(level_choice, "beginner")

    hours = input(f"{GREEN}Preferred study hours (e.g. 09:00-17:00): {RESET}").strip() or "09:00-17:00"

    user = upsert_user(name=name, bio=bio, current_level=level, preferred_hours=hours)
    print(f"\n{GREEN}✅ Profile created for {user['name']}!{RESET}")

    # Ask about goals
    print(f"\n{CYAN}Let's set your first goal:{RESET}")
    goal_title = input(f"{GREEN}Goal title (e.g. 'Become an ML Engineer'): {RESET}").strip()
    if goal_title:
        target_role = input(f"{GREEN}Target role/position: {RESET}").strip()
        description = input(f"{GREEN}Brief description: {RESET}").strip()
        priority = input(f"{GREEN}Priority (low/medium/high/critical) [medium]: {RESET}").strip() or "medium"
        target_date = input(f"{GREEN}Target date (YYYY-MM-DD) [optional]: {RESET}").strip() or None

        goal = add_goal(
            user_id=user["id"],
            goal_title=goal_title,
            description=description,
            target_role=target_role,
            priority=priority,
            target_date=target_date,
        )
        print(f"{GREEN}✅ Goal '{goal['goal_title']}' created!{RESET}")

    print(f"\n{CYAN}Setup complete! Start chatting with Liebchen.{RESET}\n")
    return user["id"]


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Liebchen AI Agent CLI")
    parser.add_argument("--startup", action="store_true", help="Trigger startup greeting")
    parser.add_argument("--setup", action="store_true", help="Run first-time setup")
    args = parser.parse_args()

    print(BANNER)

    # ── Initialize Database ────────────────────────────────────────────────
    print(f"{DIM}Initializing database...{RESET}")
    initialize_database()

    # ── First-time setup check ─────────────────────────────────────────────
    user = get_user(1)
    if args.setup or user is None:
        user_id = run_setup_wizard()
    else:
        user_id = user["id"]
        print(f"{GREEN}Welcome back, {user['name']}!{RESET}")

    # ── Initialize LLM & Agent ─────────────────────────────────────────────
    print(f"{DIM}Connecting to Ollama...{RESET}")
    llm = get_llm_with_health_check()

    print(f"{DIM}Building agent graph...{RESET}")
    graph, checkpointer = build_graph(llm=llm)

    # Thread ID for conversation persistence
    thread_id = f"cli-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    print(f"{DIM}Thread: {thread_id}{RESET}\n")

    # ── Startup greeting ───────────────────────────────────────────────────
    if args.startup:
        startup_msg = create_startup_message(user_id)
        print(f"{DIM}Triggering startup greeting...{RESET}\n")
        result = graph.invoke(
            {"messages": [startup_msg], "user_id": user_id},
            config=config,
        )
        ai_msg = result["messages"][-1]
        print(f"{CYAN}{BOLD}Liebchen:{RESET} {ai_msg.content}\n")

    # ── Interactive REPL ───────────────────────────────────────────────────
    while True:
        try:
            user_input = input(f"{GREEN}{BOLD}You:{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Goodbye! Keep learning! 📚{RESET}")
            break

        if not user_input:
            continue

        # Handle special commands
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]

            if cmd in ("/quit", "/exit", "/q"):
                print(f"{YELLOW}Goodbye! Keep learning! 📚{RESET}")
                break

            elif cmd == "/help":
                print(HELP_TEXT)
                continue

            elif cmd == "/setup":
                user_id = run_setup_wizard()
                continue

            elif cmd == "/clear":
                thread_id = f"cli-{uuid.uuid4().hex[:8]}"
                config = {"configurable": {"thread_id": thread_id}}
                print(f"{DIM}New conversation started. Thread: {thread_id}{RESET}\n")
                continue

            elif cmd == "/tasks":
                user_input = "What are my pending tasks? Use the get_pending_tasks tool."

            elif cmd == "/schedule":
                user_input = "Show me my timetable. Use the update_timetable tool with action 'view'."

            elif cmd == "/progress":
                user_input = "How is my overall progress? Use the get_pending_tasks tool to check."

            elif cmd == "/startup":
                startup_msg = create_startup_message(user_id)
                user_input = startup_msg.content

        # ── Send to Agent ──────────────────────────────────────────────────
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=user_input)], "user_id": user_id},
                config=config,
            )

            # Extract the final AI message
            ai_msg = result["messages"][-1]
            print(f"\n{CYAN}{BOLD}Liebchen:{RESET} {ai_msg.content}\n")

        except Exception as e:
            print(f"\n{RED}Error: {e}{RESET}")
            print(f"{DIM}Try again or type /help for commands.{RESET}\n")


if __name__ == "__main__":
    main()
