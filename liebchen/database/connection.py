"""
SQLite connection manager.

Provides a thread-safe connection factory and a context manager
for transactional database access.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from liebchen.config import DB_PATH


from db.pool import ConnectionPool


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """
    Get the shared HDD-optimized SQLite connection.
    """
    return ConnectionPool.get()


@contextmanager
def get_db(db_path: Path | str | None = None):
    """
    Context manager yielding the shared connection.
    Does not close the underlying connection on exit (reused).
    """
    conn = ConnectionPool.get()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
