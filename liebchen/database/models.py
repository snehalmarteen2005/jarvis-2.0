"""
SQLite database schema and helper functions.

This module defines the complete schema for the Liebchen agent and
provides CRUD helpers that the LangGraph tools call into.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, date
from typing import Any

from liebchen.database.connection import get_db


# ═══════════════════════════════════════════════════════════════════════════════
#  SCHEMA DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    bio             TEXT    DEFAULT '',
    current_level   TEXT    DEFAULT 'beginner',   -- beginner | intermediate | advanced
    preferred_hours TEXT    DEFAULT '09:00-17:00', -- study window
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Skills ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skills (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_name        TEXT    NOT NULL,
    proficiency_level TEXT    DEFAULT 'novice',  -- novice | beginner | intermediate | advanced | expert
    category          TEXT    DEFAULT 'general', -- e.g. programming, math, science
    assessed_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Goals ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_title   TEXT    NOT NULL,
    description  TEXT    DEFAULT '',
    target_role  TEXT    DEFAULT '',              -- e.g. "ML Engineer", "Full-Stack Dev"
    priority     TEXT    DEFAULT 'medium',        -- low | medium | high | critical
    target_date  TEXT    DEFAULT NULL,            -- ISO date
    status       TEXT    DEFAULT 'active',        -- active | completed | paused | cancelled
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Learning Plans ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning_plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id     INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    plan_title  TEXT    NOT NULL,
    description TEXT    DEFAULT '',
    steps_json  TEXT    DEFAULT '[]',             -- JSON array of step objects
    status      TEXT    DEFAULT 'draft',          -- draft | active | completed | archived
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Timetable Entries ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS timetable_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id           INTEGER REFERENCES learning_plans(id) ON DELETE SET NULL,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic             TEXT    NOT NULL,
    description       TEXT    DEFAULT '',
    scheduled_date    TEXT    NOT NULL,            -- ISO date
    start_time        TEXT    DEFAULT '09:00',
    end_time          TEXT    DEFAULT '10:00',
    status            TEXT    DEFAULT 'pending',   -- pending | in_progress | completed | skipped | rescheduled
    estimated_minutes INTEGER DEFAULT 60,
    actual_minutes    INTEGER DEFAULT NULL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Progress Logs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS progress_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id          INTEGER REFERENCES timetable_entries(id) ON DELETE SET NULL,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notes             TEXT    DEFAULT '',
    completion_pct    REAL    DEFAULT 0.0,         -- 0.0 to 100.0
    difficulty_rating TEXT    DEFAULT 'medium',     -- easy | medium | hard | very_hard
    logged_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_skills_user        ON skills(user_id);
CREATE INDEX IF NOT EXISTS idx_goals_user         ON goals(user_id);
CREATE INDEX IF NOT EXISTS idx_plans_user         ON learning_plans(user_id);
CREATE INDEX IF NOT EXISTS idx_timetable_user     ON timetable_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_timetable_date     ON timetable_entries(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_progress_user      ON progress_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_progress_entry     ON progress_logs(entry_id);
"""


def initialize_database() -> None:
    """Create all tables if they don't already exist."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)


# ═══════════════════════════════════════════════════════════════════════════════
#  CRUD HELPERS — Used by agent tools
# ═══════════════════════════════════════════════════════════════════════════════

# ── Users ──────────────────────────────────────────────────────────────────────

def upsert_user(
    name: str,
    bio: str = "",
    current_level: str = "beginner",
    preferred_hours: str = "09:00-17:00",
    user_id: int | None = None,
) -> dict[str, Any]:
    """Create or update a user profile. Returns the user row as a dict."""
    with get_db() as conn:
        if user_id:
            conn.execute(
                """UPDATE users
                   SET name=?, bio=?, current_level=?, preferred_hours=?, updated_at=datetime('now')
                   WHERE id=?""",
                (name, bio, current_level, preferred_hours, user_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO users (name, bio, current_level, preferred_hours)
                   VALUES (?, ?, ?, ?)""",
                (name, bio, current_level, preferred_hours),
            )
            user_id = cursor.lastrowid

        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row)


def get_user(user_id: int = 1) -> dict[str, Any] | None:
    """Fetch a user by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


# ── Skills ─────────────────────────────────────────────────────────────────────

def add_skill(user_id: int, skill_name: str, proficiency: str = "novice", category: str = "general") -> dict:
    """Add a skill record for a user."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO skills (user_id, skill_name, proficiency_level, category) VALUES (?, ?, ?, ?)",
            (user_id, skill_name, proficiency, category),
        )
        row = conn.execute("SELECT * FROM skills WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def get_skills(user_id: int) -> list[dict]:
    """Get all skills for a user."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM skills WHERE user_id=? ORDER BY category, skill_name", (user_id,)).fetchall()
        return [dict(r) for r in rows]


# ── Goals ──────────────────────────────────────────────────────────────────────

def add_goal(
    user_id: int,
    goal_title: str,
    description: str = "",
    target_role: str = "",
    priority: str = "medium",
    target_date: str | None = None,
) -> dict:
    """Create a new goal for a user."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO goals (user_id, goal_title, description, target_role, priority, target_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, goal_title, description, target_role, priority, target_date),
        )
        row = conn.execute("SELECT * FROM goals WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def get_goals(user_id: int, status: str = "active") -> list[dict]:
    """Get goals for a user, optionally filtered by status."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM goals WHERE user_id=? AND status=? ORDER BY priority DESC",
            (user_id, status),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Learning Plans ─────────────────────────────────────────────────────────────

def create_learning_plan(
    user_id: int,
    plan_title: str,
    description: str = "",
    steps: list[dict] | None = None,
    goal_id: int | None = None,
) -> dict:
    """Create a new learning plan with structured steps."""
    steps_json = json.dumps(steps or [])
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO learning_plans (user_id, goal_id, plan_title, description, steps_json, status)
               VALUES (?, ?, ?, ?, ?, 'active')""",
            (user_id, goal_id, plan_title, description, steps_json),
        )
        row = conn.execute("SELECT * FROM learning_plans WHERE id=?", (cursor.lastrowid,)).fetchone()
        result = dict(row)
        result["steps"] = json.loads(result["steps_json"])
        return result


def get_learning_plans(user_id: int) -> list[dict]:
    """Get all learning plans for a user."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM learning_plans WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        plans = []
        for r in rows:
            d = dict(r)
            d["steps"] = json.loads(d.get("steps_json", "[]"))
            plans.append(d)
        return plans


# ── Timetable ──────────────────────────────────────────────────────────────────

def add_timetable_entry(
    user_id: int,
    topic: str,
    scheduled_date: str,
    start_time: str = "09:00",
    end_time: str = "10:00",
    description: str = "",
    estimated_minutes: int = 60,
    plan_id: int | None = None,
) -> dict:
    """Add a single timetable entry."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO timetable_entries
               (plan_id, user_id, topic, description, scheduled_date, start_time, end_time, estimated_minutes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan_id, user_id, topic, description, scheduled_date, start_time, end_time, estimated_minutes),
        )
        row = conn.execute("SELECT * FROM timetable_entries WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def get_timetable(user_id: int, date_str: str | None = None, status: str | None = None) -> list[dict]:
    """
    Get timetable entries. Optionally filter by date and/or status.
    If no date is provided, returns all future + today's entries.
    """
    with get_db() as conn:
        query = "SELECT * FROM timetable_entries WHERE user_id=?"
        params: list[Any] = [user_id]

        if date_str:
            query += " AND scheduled_date=?"
            params.append(date_str)
        else:
            query += " AND scheduled_date >= date('now')"

        if status:
            query += " AND status=?"
            params.append(status)

        query += " ORDER BY scheduled_date, start_time"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def update_timetable_entry(entry_id: int, **fields) -> dict | None:
    """Update specific fields on a timetable entry."""
    allowed = {"topic", "description", "scheduled_date", "start_time", "end_time",
               "status", "estimated_minutes", "actual_minutes"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return None

    with get_db() as conn:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [entry_id]
        conn.execute(f"UPDATE timetable_entries SET {set_clause} WHERE id=?", values)
        row = conn.execute("SELECT * FROM timetable_entries WHERE id=?", (entry_id,)).fetchone()
        return dict(row) if row else None


# ── Progress ───────────────────────────────────────────────────────────────────

def log_progress(
    user_id: int,
    entry_id: int | None = None,
    notes: str = "",
    completion_pct: float = 0.0,
    difficulty_rating: str = "medium",
) -> dict:
    """Log a progress entry."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO progress_logs (entry_id, user_id, notes, completion_pct, difficulty_rating)
               VALUES (?, ?, ?, ?, ?)""",
            (entry_id, user_id, notes, completion_pct, difficulty_rating),
        )
        row = conn.execute("SELECT * FROM progress_logs WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def get_progress_summary(user_id: int) -> dict:
    """Get an aggregate progress summary for a user."""
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM timetable_entries WHERE user_id=?", (user_id,)
        ).fetchone()["cnt"]

        completed = conn.execute(
            "SELECT COUNT(*) as cnt FROM timetable_entries WHERE user_id=? AND status='completed'",
            (user_id,),
        ).fetchone()["cnt"]

        pending = conn.execute(
            "SELECT COUNT(*) as cnt FROM timetable_entries WHERE user_id=? AND status='pending'",
            (user_id,),
        ).fetchone()["cnt"]

        avg_completion = conn.execute(
            "SELECT COALESCE(AVG(completion_pct), 0) as avg_pct FROM progress_logs WHERE user_id=?",
            (user_id,),
        ).fetchone()["avg_pct"]

        return {
            "total_entries": total,
            "completed": completed,
            "pending": pending,
            "skipped_or_rescheduled": total - completed - pending,
            "average_completion_pct": round(avg_completion, 1),
            "completion_rate_pct": round((completed / total * 100) if total > 0 else 0, 1),
        }
