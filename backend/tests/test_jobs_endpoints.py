"""Tests for the resumable upload progress view backend foundation.

Covers:

* GET /api/uploads/jobs/recent returns [] when there are no uploads at all.
* Jobs are returned ordered by started_at DESC.
* Status derivation handles every combination:
    - all completed -> 'completed'
    - all failed    -> 'failed'
    - mix of completed + failed -> 'partial'
    - any pending/uploading -> 'running'
* GET /api/uploads/job/{job_id} 404s on an unknown id.
* GET /api/uploads/job/{job_id} returns the rows in created_at ASC, each row
  carries the sub-stage error fields (verification_error / thumbnail_error /
  comment_error) — null-by-default on a fresh row.
* The finalize task persists thumbnail_error to the Upload row when
  set_thumbnail raises, so a cold-loaded job can show the failure.
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

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
# Engine helper
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path):
    """FastAPI TestClient backed by a fresh per-test SQLite DB."""
    engine = _make_engine(tmp_path / "jobs_endpoints_test.db")
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


def _seed_channel(session) -> int:
    """Insert a Project -> Account -> Channel chain. Returns channel.id."""
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

    channel = Channel(
        account_id=account.id,
        channel_id="UCabc",
        channel_name="Chan",
        language_code="en",
    )
    session.add(channel)
    session.commit()
    return channel.id


def _seed_job(
    session,
    *,
    job_id: str,
    channel_id: int,
    statuses: list[str],
    base_created_at: datetime,
) -> None:
    """Add one Upload row per status, all with the same job_id and channel."""
    for i, status in enumerate(statuses):
        session.add(
            Upload(
                job_id=job_id,
                channel_id=channel_id,
                file_path=f"/tmp/{job_id}_{i}.mp4",
                file_name=f"{job_id}_{i}.mp4",
                title=f"t{i}",
                status=status,
                created_at=base_created_at + timedelta(seconds=i),
                quota_cost=100,
            )
        )
    session.commit()


# ---------------------------------------------------------------------------
# 1. /jobs/recent — empty
# ---------------------------------------------------------------------------


def test_jobs_recent_empty(client):
    resp = client.get("/api/uploads/jobs/recent")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# ---------------------------------------------------------------------------
# 2. /jobs/recent — sorted descending by started_at
# ---------------------------------------------------------------------------


def test_jobs_recent_sorted_descending(client):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        channel_id = _seed_channel(session)
        older = datetime(2024, 1, 1, 12, 0, 0)
        newer = datetime(2024, 6, 1, 12, 0, 0)
        _seed_job(
            session,
            job_id="job-old",
            channel_id=channel_id,
            statuses=["completed"],
            base_created_at=older,
        )
        _seed_job(
            session,
            job_id="job-new",
            channel_id=channel_id,
            statuses=["completed"],
            base_created_at=newer,
        )
    finally:
        session.close()

    resp = client.get("/api/uploads/jobs/recent")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [j["job_id"] for j in body] == ["job-new", "job-old"], body


# ---------------------------------------------------------------------------
# 3. /jobs/recent — status derivation across the four cases
# ---------------------------------------------------------------------------


def test_jobs_recent_status_derivation(client):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        channel_id = _seed_channel(session)
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        # job-completed: all completed
        _seed_job(
            session,
            job_id="job-completed",
            channel_id=channel_id,
            statuses=["completed", "completed"],
            base_created_at=t0,
        )
        # job-failed: all failed
        _seed_job(
            session,
            job_id="job-failed",
            channel_id=channel_id,
            statuses=["failed", "failed"],
            base_created_at=t0 + timedelta(minutes=1),
        )
        # job-partial: mix completed + failed
        _seed_job(
            session,
            job_id="job-partial",
            channel_id=channel_id,
            statuses=["completed", "failed"],
            base_created_at=t0 + timedelta(minutes=2),
        )
        # job-running: at least one pending or uploading
        _seed_job(
            session,
            job_id="job-running",
            channel_id=channel_id,
            statuses=["completed", "uploading", "pending"],
            base_created_at=t0 + timedelta(minutes=3),
        )
    finally:
        session.close()

    resp = client.get("/api/uploads/jobs/recent")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_id = {j["job_id"]: j for j in body}
    assert by_id["job-completed"]["status"] == "completed", by_id["job-completed"]
    assert by_id["job-failed"]["status"] == "failed", by_id["job-failed"]
    assert by_id["job-partial"]["status"] == "partial", by_id["job-partial"]
    assert by_id["job-running"]["status"] == "running", by_id["job-running"]

    # in_flight sanity: running job has 2 (uploading + pending)
    assert by_id["job-running"]["in_flight"] == 2
    # Counts on the partial job
    assert by_id["job-partial"]["completed"] == 1
    assert by_id["job-partial"]["failed"] == 1
    assert by_id["job-partial"]["total"] == 2


# ---------------------------------------------------------------------------
# 4. /job/{unknown_id} -> 404
# ---------------------------------------------------------------------------


def test_get_job_unknown_returns_404(client):
    resp = client.get("/api/uploads/job/unknown-id")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Job not found"


# ---------------------------------------------------------------------------
# 5. /job/{job_id} -> rows in created_at ASC, includes sub-stage error fields
# ---------------------------------------------------------------------------


def test_get_job_returns_rows_with_substage_error_fields(client):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        channel_id = _seed_channel(session)
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        _seed_job(
            session,
            job_id="job-shape",
            channel_id=channel_id,
            statuses=["completed", "completed", "completed"],
            base_created_at=t0,
        )
    finally:
        session.close()

    resp = client.get("/api/uploads/job/job-shape")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 3, body

    # Ordered ascending by created_at
    timestamps = [row["created_at"] for row in body]
    assert timestamps == sorted(timestamps), timestamps

    # Each row exposes the three sub-stage error columns (null by default)
    for row in body:
        assert "verification_error" in row, row
        assert "thumbnail_error" in row, row
        assert "comment_error" in row, row
        assert row["verification_error"] is None
        assert row["thumbnail_error"] is None
        assert row["comment_error"] is None
        # channel_has_default_comment is derived from the channel; the seed
        # channel has no default_comment set, so this must be False.
        assert "channel_has_default_comment" in row, row
        assert row["channel_has_default_comment"] is False


def test_get_job_channel_has_default_comment_true_when_set(client):
    """When the channel has a non-empty default_comment, the per-upload row
    surfaces channel_has_default_comment=True so the UI knows to render the
    Comentário pill in the reconstructed timeline."""
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        channel_id = _seed_channel(session)
        # Update the seeded channel to carry a default_comment
        ch = session.query(Channel).filter(Channel.id == channel_id).first()
        assert ch is not None
        ch.default_comment = "Obrigado por assistir!"
        session.commit()

        t0 = datetime(2024, 1, 1, 12, 0, 0)
        _seed_job(
            session,
            job_id="job-with-comment",
            channel_id=channel_id,
            statuses=["completed"],
            base_created_at=t0,
        )
    finally:
        session.close()

    resp = client.get("/api/uploads/job/job-with-comment")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["channel_has_default_comment"] is True, body[0]


# ---------------------------------------------------------------------------
# 6. _finalize_after_insert persists thumbnail_error when set_thumbnail raises
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_finalize_persists_thumbnail_error_on_set_thumbnail_raise(
    tmp_path, monkeypatch
):
    """When set_thumbnail raises, the Upload row's thumbnail_error column must
    be populated so a finished job's timeline can reconstruct the failure
    on cold load — not just the websocket event stream."""
    engine = _make_engine(tmp_path / "finalize_persist.db")
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed
    session = TestSessionLocal()
    try:
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
        channel = Channel(
            account_id=account.id,
            channel_id="UCabc",
            channel_name="Chan",
            language_code="en",
        )
        session.add(channel)
        session.commit()
        thumb_file = tmp_path / "thumb.jpg"
        thumb_file.write_bytes(b"\xff\xd8\xff\xd9")
        upload = Upload(
            job_id="job-persist",
            channel_id=channel.id,
            file_path="/tmp/video.mp4",
            file_name="video.mp4",
            title="t",
            description="",
            tags="",
            privacy="private",
            status="pending",
            thumbnail_path=str(thumb_file),
            quota_cost=100,
        )
        session.add(upload)
        session.commit()
        upload_id = upload.id
        project_id = project.id
    finally:
        session.close()

    from backend.services import upload_manager as um_module

    monkeypatch.setattr(um_module, "SessionLocal", TestSessionLocal)

    # Fake yt service: verification reports success immediately
    fake_yt = MagicMock(name="yt_service")
    videos_obj = MagicMock()
    req = MagicMock()
    req.execute.return_value = {
        "items": [
            {
                "status": {"uploadStatus": "processed"},
                "processingDetails": {"processingStatus": "succeeded"},
            }
        ]
    }
    videos_obj.list.return_value = req
    fake_yt.videos.return_value = videos_obj

    boom = RuntimeError("thumbnail API down")

    async def _noop_callback(_payload):
        pass

    with patch.object(um_module.youtube_service, "set_thumbnail", side_effect=boom), \
         patch("backend.services.upload_manager.compress_thumbnail", return_value=None), \
         patch.object(um_module.asyncio, "sleep", new=AsyncMock(return_value=None)):
        _run(
            um_module.upload_manager._finalize_after_insert(
                job_id="job-persist",
                upload_id=upload_id,
                video_id="vidX",
                youtube_url="https://youtu.be/vidX",
                yt_service=fake_yt,
                thumbnail_path=str(thumb_file),
                default_comment=None,
                project_id=project_id,
                callback=_noop_callback,
            )
        )

    # Re-open the DB and assert thumbnail_error is persisted
    session = TestSessionLocal()
    try:
        upload = session.query(Upload).filter(Upload.id == upload_id).first()
        assert upload is not None
        assert upload.thumbnail_error is not None, "thumbnail_error must be persisted"
        assert "thumbnail API down" in upload.thumbnail_error, upload.thumbnail_error
        # Upload still completes — video is on YouTube
        assert upload.status == "completed", upload.status
    finally:
        session.close()
        engine.dispose()
