"""Regression tests: API quota must be recorded once per attempted upload,
including FAILED uploads, because YouTube debits videos.insert server-side
regardless of whether the client-side upload reports success.

Bug:  upload_manager.process_job called quota_service.record_usage only inside
the success branch. Uploads that failed mid-flight (e.g. transient network
error after videos.insert was dispatched) were not counted, so the sidebar
showed "0 / 10,000" even after the user had burned real quota.

Fix:  record quota right after credentials/yt_service are resolved -- before
the upload is dispatched. That gives us:
    - failure before credentials resolve     -> no charge (no API call hit)
    - failure during/after videos.insert     -> charge (YouTube debited us)
    - success                                -> charge exactly once

These three tests pin that contract.
"""
import asyncio
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.project import Project
from backend.models.account import Account
from backend.models.channel import Channel
from backend.models.upload import Upload
from backend.models.quota import QuotaUsage  # noqa: F401 -- needed for table creation


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


def _make_engine(db_path):
    """Spin up a fresh SQLite DB configured like the real app (WAL + timeout)."""
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
def db_setup(tmp_path, monkeypatch):
    """Build a fresh DB, seed Project/Account/Channel/Upload, patch SessionLocal
    inside upload_manager so process_job uses our test DB.
    """
    engine = _make_engine(tmp_path / "quota_test.db")
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed minimal fixtures.
    session = TestSessionLocal()
    try:
        project = Project(name="P1", client_secret_path="/fake/secret.json", daily_quota_limit=10000)
        session.add(project)
        session.commit()

        account = Account(email="a@b.com", project_id=project.id, token_path="/fake/token.json")
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

        upload = Upload(
            job_id="job-1",
            channel_id=channel.id,
            file_path=str(tmp_path / "video.mp4"),
            file_name="video.mp4",
            title="t",
            description="",
            tags="",
            privacy="private",
            status="pending",
            quota_cost=100,
        )
        session.add(upload)
        session.commit()
        upload_id = upload.id
        project_id = project.id
    finally:
        session.close()

    # Force upload_manager.SessionLocal to use our test engine.
    from backend.services import upload_manager as um_module
    monkeypatch.setattr(um_module, "SessionLocal", TestSessionLocal)

    return {
        "engine": engine,
        "SessionLocal": TestSessionLocal,
        "upload_id": upload_id,
        "project_id": project_id,
    }


def _run(coro):
    """Run an async coroutine in a fresh loop (Windows-friendly)."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_failed_upload_still_records_quota(db_setup):
    """videos.insert raised after credentials were resolved -> YouTube charged us,
    so we MUST record the quota even though the upload status is 'failed'."""
    from backend.services import upload_manager as um_module

    fake_yt_service = MagicMock(name="yt_service")

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt_service), \
         patch.object(um_module.youtube_service, "upload_video", side_effect=Exception("network boom")), \
         patch.object(um_module.quota_service, "record_usage") as mock_record:

        # Skip the initial 1s sleep to keep the test fast.
        async def _no_sleep(*_args, **_kwargs):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-1"))

        # Quota recorded exactly once with the upload's quota_cost.
        assert mock_record.call_count == 1
        _, kwargs = mock_record.call_args
        assert kwargs["project_id"] == db_setup["project_id"]
        assert kwargs["units"] == 100

    # Sanity: the upload itself is marked failed.
    session = db_setup["SessionLocal"]()
    try:
        upload = session.query(Upload).filter(Upload.id == db_setup["upload_id"]).first()
        assert upload.status == "failed"
        assert "network boom" in (upload.error_message or "")
    finally:
        session.close()


def test_successful_upload_records_quota_exactly_once(db_setup):
    """A successful upload must NOT double-count (the bug fix removed the old
    success-only call; ensure we didn't accidentally leave both in place)."""
    from backend.services import upload_manager as um_module

    fake_yt_service = MagicMock(name="yt_service")

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt_service), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vid123", "youtube_url": "https://youtu.be/vid123"},
         ), \
         patch.object(um_module.quota_service, "record_usage") as mock_record:

        async def _no_sleep(*_args, **_kwargs):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-1"))

        assert mock_record.call_count == 1, (
            f"expected exactly one quota record call, got {mock_record.call_count} "
            f"(double-counting regression?)"
        )
        _, kwargs = mock_record.call_args
        assert kwargs["project_id"] == db_setup["project_id"]
        assert kwargs["units"] == 100

    session = db_setup["SessionLocal"]()
    try:
        upload = session.query(Upload).filter(Upload.id == db_setup["upload_id"]).first()
        assert upload.status == "completed"
    finally:
        session.close()


def test_no_quota_recorded_when_credentials_fail(db_setup):
    """If load_credentials returns None we error out BEFORE dispatching to
    YouTube -- no API call was made, so we must NOT charge quota."""
    from backend.services import upload_manager as um_module

    with patch.object(um_module.oauth_service, "load_credentials", return_value=None), \
         patch.object(um_module.oauth_service, "get_youtube_service") as mock_get_service, \
         patch.object(um_module.youtube_service, "upload_video") as mock_upload, \
         patch.object(um_module.quota_service, "record_usage") as mock_record:

        async def _no_sleep(*_args, **_kwargs):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-1"))

        mock_get_service.assert_not_called()
        mock_upload.assert_not_called()
        assert mock_record.call_count == 0, (
            "quota must not be charged when no API request reached YouTube"
        )

    session = db_setup["SessionLocal"]()
    try:
        upload = session.query(Upload).filter(Upload.id == db_setup["upload_id"]).first()
        assert upload.status == "failed"
        assert "Invalid credentials" in (upload.error_message or "")
    finally:
        session.close()
