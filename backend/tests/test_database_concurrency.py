"""Regression tests for the intermittent 500 on /api/quota/summary.

Root cause: the SQLite engine used the default rollback journal (no WAL) and the
pysqlite default busy timeout, so a read overlapping a long-held writer lock
raised 'database is locked' -> HTTP 500. The fix enables WAL + a 30s busy
timeout on every connection. These tests assert that hardening is active and
that a reader survives a concurrent writer holding an exclusive lock.
"""
import sqlite3
import threading
import time
import os

import pytest
from sqlalchemy import create_engine, event, text


def _make_sqlite_engine(db_path):
    """Build an engine configured exactly like backend.database (WAL + timeout)."""
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

    return engine


def test_app_engine_uses_wal_and_busy_timeout():
    """The real application engine must run in WAL with a busy timeout set."""
    from backend.database import engine

    raw = engine.raw_connection()
    try:
        c = raw.driver_connection
        journal_mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = c.execute("PRAGMA busy_timeout").fetchone()[0]
        assert journal_mode.lower() == "wal"
        assert busy_timeout >= 30000
    finally:
        raw.close()


def test_reader_survives_concurrent_writer(tmp_path):
    """Under WAL a reader must NOT get 'database is locked' while a writer holds
    a write lock -- the exact failure mode behind the 500."""
    db_path = tmp_path / "concurrency.db"
    engine = _make_sqlite_engine(str(db_path))

    # seed a table to read from
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.execute(text("INSERT INTO t (x) VALUES (1)"))
        conn.commit()

    lock_held = threading.Event()
    release = threading.Event()

    def writer():
        # raw connection holding a write transaction while the reader runs
        w = sqlite3.connect(str(db_path), timeout=30)
        w.execute("PRAGMA busy_timeout=30000")
        w.isolation_level = None
        w.execute("BEGIN IMMEDIATE")
        w.execute("INSERT INTO t (x) VALUES (2)")
        lock_held.set()
        release.wait(timeout=5)
        w.execute("COMMIT")
        w.close()

    t = threading.Thread(target=writer)
    t.start()
    assert lock_held.wait(timeout=5), "writer never acquired lock"

    # Reader runs while the writer holds its lock. In WAL this succeeds.
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT count(*) FROM t")).fetchone()
            assert rows[0] >= 1
    finally:
        release.set()
        t.join()


class _StubProject:
    def __init__(self, id, name, daily_quota_limit):
        self.id = id
        self.name = name
        self.daily_quota_limit = daily_quota_limit


def test_get_summary_happy_path():
    """get_summary returns one item per project with correct math."""
    from unittest.mock import MagicMock
    from backend.services.quota_service import quota_service

    db = MagicMock()
    db.query.return_value.all.return_value = [
        _StubProject(1, "P1", 10000),
    ]
    # no usage row today
    db.query.return_value.filter.return_value.first.return_value = None

    items = quota_service.get_summary(db)
    assert len(items) == 1
    assert items[0].daily_limit == 10000
    assert items[0].units_used == 0
    assert items[0].remaining == 10000
    assert items[0].percentage_used == 0.0
