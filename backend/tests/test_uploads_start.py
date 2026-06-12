"""Tests for POST /api/uploads/start scheduled_at handling.

Root-cause coverage for the auto-agendar bug:

* Per-entry ``RoutingEntry.scheduled_at`` survives Pydantic validation and
  is persisted to the Upload row (regression: the schema previously omitted
  the field, so Pydantic dropped it silently and every row got scheduled_at
  = None on the YouTube call, dumping videos as Private with no schedule).
* The legacy job-level ``scheduled_at`` + ``stagger_minutes`` flow still
  produces evenly staggered Upload rows when entries don't carry their own.
* Per-entry value wins over the job-level value when both are provided.
* No scheduling at all -> Upload.scheduled_at == None on every row.
* When any entry is scheduled, the whole job's privacy is forced to
  'private' regardless of the request body, because YouTube only honours
  publishAt on private videos.

The /start handler also kicks off ``upload_manager.process_job`` via
BackgroundTasks. We mock it to a no-op AsyncMock so the test exercises only
the create-job DB persistence path.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models.account import Account
from backend.models.channel import Channel
from backend.models.channel_group import ChannelGroup  # noqa: F401 -- table creation
from backend.models.project import Project
from backend.models.quota import QuotaUsage  # noqa: F401 -- table creation
from backend.models.upload import Upload


# ---------------------------------------------------------------------------
# Engine + client fixture
# ---------------------------------------------------------------------------


def _make_engine(db_path):
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

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def client(tmp_path):
    engine = _make_engine(tmp_path / "uploads_start_test.db")
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    test_client._SessionLocal = TestSessionLocal  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _seed_channels(session, n: int = 1) -> list[int]:
    """Insert a Project + Account + N Channels. Returns the channel ids."""
    project = Project(
        name="P", client_secret_path="/fake/secret.json", daily_quota_limit=10000
    )
    session.add(project)
    session.commit()

    account = Account(
        email="a@b.com", project_id=project.id, token_path="/fake/token.json"
    )
    session.add(account)
    session.commit()

    ids: list[int] = []
    for i in range(n):
        ch = Channel(
            account_id=account.id,
            channel_id=f"UCabc{i}",
            channel_name=f"Chan{i}",
            language_code="en",
        )
        session.add(ch)
        session.commit()
        ids.append(ch.id)
    return ids


def _routing_entry(channel_id: int, *, file_name: str, scheduled_at: str | None = None) -> dict:
    """Build a RoutingEntry dict for the request body. Mirrors the frontend payload."""
    d = {
        "file_name": file_name,
        "file_path": f"/tmp/{file_name}",
        "detected_language": "en",
        "detection_method": "filename",
        "channel_id": channel_id,
        "channel_name": "Chan",
        "thumbnail_path": None,
        "title": file_name.rsplit(".", 1)[0],
    }
    if scheduled_at is not None:
        d["scheduled_at"] = scheduled_at
    return d


def _normalize(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on persistence; compare against naive UTC."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------------------
# 1. Per-entry scheduled_at survives validation and reaches the DB
# ---------------------------------------------------------------------------


def test_per_entry_scheduled_at_persisted(client):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        [cid] = _seed_channels(session, n=1)
    finally:
        session.close()

    body = {
        "job_id": "job-per-entry",
        "routing": [
            _routing_entry(cid, file_name="vid1.mp4", scheduled_at="2026-06-10T15:30:00+00:00"),
        ],
        "privacy": "private",
        "description": "",
        "tags": "",
        "scheduled_at": None,
        "stagger_minutes": None,
    }

    with patch(
        "backend.services.upload_manager.upload_manager.process_job",
        new=AsyncMock(),
    ):
        resp = client.post("/api/uploads/start", json=body)

    assert resp.status_code == 200, resp.text
    assert resp.json()["job_id"] == "job-per-entry"

    session = SessionLocal()
    try:
        rows = session.query(Upload).filter(Upload.job_id == "job-per-entry").all()
        assert len(rows) == 1
        expected = datetime(2026, 6, 10, 15, 30, 0)
        assert _normalize(rows[0].scheduled_at) == expected, rows[0].scheduled_at
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 2. Legacy job-level scheduled_at + stagger still works
# ---------------------------------------------------------------------------


def test_legacy_job_level_stagger(client):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        cids = _seed_channels(session, n=3)
    finally:
        session.close()

    body = {
        "job_id": "job-stagger",
        "routing": [
            _routing_entry(cids[0], file_name="vid1.mp4"),
            _routing_entry(cids[1], file_name="vid2.mp4"),
            _routing_entry(cids[2], file_name="vid3.mp4"),
        ],
        "privacy": "private",
        "description": "",
        "tags": "",
        "scheduled_at": "2026-06-10T12:00:00+00:00",
        "stagger_minutes": 30,
    }

    with patch(
        "backend.services.upload_manager.upload_manager.process_job",
        new=AsyncMock(),
    ):
        resp = client.post("/api/uploads/start", json=body)

    assert resp.status_code == 200, resp.text

    session = SessionLocal()
    try:
        rows = (
            session.query(Upload)
            .filter(Upload.job_id == "job-stagger")
            .order_by(Upload.created_at.asc(), Upload.id.asc())
            .all()
        )
        assert len(rows) == 3
        # Map file_name -> scheduled_at so we don't rely on insertion order.
        by_name = {r.file_name: _normalize(r.scheduled_at) for r in rows}
        assert by_name["vid1.mp4"] == datetime(2026, 6, 10, 12, 0, 0)
        assert by_name["vid2.mp4"] == datetime(2026, 6, 10, 12, 30, 0)
        assert by_name["vid3.mp4"] == datetime(2026, 6, 10, 13, 0, 0)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 3. Per-entry wins over job-level
# ---------------------------------------------------------------------------


def test_per_entry_wins_over_job_level(client):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        [cid] = _seed_channels(session, n=1)
    finally:
        session.close()

    body = {
        "job_id": "job-precedence",
        "routing": [
            _routing_entry(cid, file_name="vid1.mp4", scheduled_at="2026-07-01T09:15:00+00:00"),
        ],
        "privacy": "private",
        "description": "",
        "tags": "",
        # Job-level value is DIFFERENT from per-entry; per-entry must win.
        "scheduled_at": "2026-06-10T12:00:00+00:00",
        "stagger_minutes": None,
    }

    with patch(
        "backend.services.upload_manager.upload_manager.process_job",
        new=AsyncMock(),
    ):
        resp = client.post("/api/uploads/start", json=body)

    assert resp.status_code == 200, resp.text

    session = SessionLocal()
    try:
        row = session.query(Upload).filter(Upload.job_id == "job-precedence").one()
        assert _normalize(row.scheduled_at) == datetime(2026, 7, 1, 9, 15, 0), row.scheduled_at
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 4. No scheduling at all -> scheduled_at None on every row
# ---------------------------------------------------------------------------


def test_no_scheduling_anywhere(client):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        cids = _seed_channels(session, n=2)
    finally:
        session.close()

    body = {
        "job_id": "job-no-sched",
        "routing": [
            _routing_entry(cids[0], file_name="vid1.mp4"),
            _routing_entry(cids[1], file_name="vid2.mp4"),
        ],
        "privacy": "public",
        "description": "",
        "tags": "",
        "scheduled_at": None,
        "stagger_minutes": None,
    }

    with patch(
        "backend.services.upload_manager.upload_manager.process_job",
        new=AsyncMock(),
    ):
        resp = client.post("/api/uploads/start", json=body)

    assert resp.status_code == 200, resp.text

    session = SessionLocal()
    try:
        rows = session.query(Upload).filter(Upload.job_id == "job-no-sched").all()
        assert len(rows) == 2
        for r in rows:
            assert r.scheduled_at is None, (r.file_name, r.scheduled_at)
            # privacy not coerced when no scheduling is in play
            assert r.privacy == "public", (r.file_name, r.privacy)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 5. Privacy forced to 'private' when any entry is scheduled
# ---------------------------------------------------------------------------


def test_privacy_forced_private_when_any_entry_scheduled(client):
    """Even if the client requests privacy='public', the presence of ANY
    scheduled entry coerces the whole job to private — YouTube only honours
    publishAt on private videos, so a public+scheduled row would publish
    immediately and lose its schedule."""
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        cids = _seed_channels(session, n=2)
    finally:
        session.close()

    body = {
        "job_id": "job-force-private",
        "routing": [
            # Entry 0 has no per-entry schedule
            _routing_entry(cids[0], file_name="vid1.mp4"),
            # Entry 1 carries auto-agendar schedule
            _routing_entry(cids[1], file_name="vid2.mp4", scheduled_at="2026-06-10T15:30:00+00:00"),
        ],
        "privacy": "public",
        "description": "",
        "tags": "",
        "scheduled_at": None,
        "stagger_minutes": None,
    }

    with patch(
        "backend.services.upload_manager.upload_manager.process_job",
        new=AsyncMock(),
    ):
        resp = client.post("/api/uploads/start", json=body)

    assert resp.status_code == 200, resp.text

    session = SessionLocal()
    try:
        rows = session.query(Upload).filter(Upload.job_id == "job-force-private").all()
        assert len(rows) == 2
        for r in rows:
            assert r.privacy == "private", (r.file_name, r.privacy)
    finally:
        session.close()
