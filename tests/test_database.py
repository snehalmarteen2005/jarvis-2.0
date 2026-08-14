"""
Tests for the database layer.

Uses an in-memory SQLite database for isolation.
"""

import pytest
import sqlite3
from liebchen.database.models import (
    SCHEMA_SQL,
    upsert_user,
    get_user,
    add_skill,
    get_skills,
    add_goal,
    get_goals,
    create_learning_plan,
    add_timetable_entry,
    get_timetable,
    update_timetable_entry,
    log_progress,
    get_progress_summary,
)
from liebchen.database.connection import get_db
from liebchen.config import DB_PATH


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("liebchen.config.DB_PATH", db_path)
    monkeypatch.setattr("liebchen.database.connection.DB_PATH", db_path)

    with get_db(db_path) as conn:
        conn.executescript(SCHEMA_SQL)

    return db_path


class TestUserCRUD:
    def test_create_user(self, test_db):
        user = upsert_user(name="Alice", bio="CS student", current_level="beginner")
        assert user["name"] == "Alice"
        assert user["bio"] == "CS student"
        assert user["id"] is not None

    def test_get_user(self, test_db):
        created = upsert_user(name="Bob")
        fetched = get_user(created["id"])
        assert fetched is not None
        assert fetched["name"] == "Bob"

    def test_update_user(self, test_db):
        user = upsert_user(name="Carol")
        updated = upsert_user(name="Carol Updated", bio="New bio", user_id=user["id"])
        assert updated["name"] == "Carol Updated"
        assert updated["bio"] == "New bio"


class TestSkills:
    def test_add_and_get_skills(self, test_db):
        user = upsert_user(name="Dev")
        add_skill(user["id"], "Python", "intermediate", "programming")
        add_skill(user["id"], "SQL", "beginner", "data")

        skills = get_skills(user["id"])
        assert len(skills) == 2
        assert skills[1]["skill_name"] in ("Python", "SQL")


class TestGoals:
    def test_add_and_get_goals(self, test_db):
        user = upsert_user(name="Learner")
        add_goal(user["id"], "Become an ML Engineer", priority="high", target_role="ML Engineer")

        goals = get_goals(user["id"])
        assert len(goals) == 1
        assert goals[0]["goal_title"] == "Become an ML Engineer"
        assert goals[0]["priority"] == "high"


class TestTimetable:
    def test_add_and_view_entries(self, test_db):
        user = upsert_user(name="Student")
        add_timetable_entry(
            user_id=user["id"],
            topic="Linear Algebra",
            scheduled_date="2099-01-01",  # Far future to always show
            start_time="10:00",
            end_time="11:00",
        )

        entries = get_timetable(user["id"])
        assert len(entries) == 1
        assert entries[0]["topic"] == "Linear Algebra"

    def test_update_entry_status(self, test_db):
        user = upsert_user(name="Student")
        entry = add_timetable_entry(
            user_id=user["id"],
            topic="Calculus",
            scheduled_date="2099-01-02",
        )
        updated = update_timetable_entry(entry["id"], status="completed")
        assert updated["status"] == "completed"


class TestProgress:
    def test_log_and_summarize(self, test_db):
        user = upsert_user(name="Tracker")
        entry = add_timetable_entry(
            user_id=user["id"],
            topic="Testing",
            scheduled_date="2099-01-01",
        )

        log_progress(user["id"], entry["id"], "Good session", 100.0, "easy")
        summary = get_progress_summary(user["id"])
        assert summary["total_entries"] == 1
        assert summary["average_completion_pct"] == 100.0
