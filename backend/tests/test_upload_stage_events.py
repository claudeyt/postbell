"""Tests for the multi-stage upload event timeline.

These pin down the callback events emitted by UploadManager.process_job:

  Stage 3 (verify on YouTube):
      youtube_processing_started -> youtube_processing_progress (>=1) -> youtube_processing_completed

  Stage 4 (thumbnail): thumbnail_applying emitted only when upload.thumbnail_path is set.
  Stage 5 (comment):   comment_posting   emitted only when channel.default_comment is set.

Polling failure must NOT mark the upload as failed (the video.insert already
succeeded — the polling is purely informational).
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
# Helpers
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


def _seed(SessionLocal, *, thumbnail_path=None, default_comment=""):
    session = SessionLocal()
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
            default_comment=default_comment,
        )
        session.add(channel)
        session.commit()

        upload = Upload(
            job_id="job-stage",
            channel_id=channel.id,
            file_path="/tmp/video.mp4",
            file_name="video.mp4",
            title="t",
            description="",
            tags="",
            privacy="private",
            status="pending",
            thumbnail_path=thumbnail_path,
            quota_cost=100,
        )
        session.add(upload)
        session.commit()
        return upload.id, project.id
    finally:
        session.close()


@pytest.fixture()
def db_factory(tmp_path, monkeypatch):
    """Return a factory that builds a fresh DB per test, optionally with
    thumbnail/default_comment values."""
    counter = {"n": 0}

    def make(*, thumbnail_path=None, default_comment=""):
        counter["n"] += 1
        engine = _make_engine(tmp_path / f"stage_test_{counter['n']}.db")
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        upload_id, project_id = _seed(
            TestSessionLocal,
            thumbnail_path=thumbnail_path,
            default_comment=default_comment,
        )
        from backend.services import upload_manager as um_module
        monkeypatch.setattr(um_module, "SessionLocal", TestSessionLocal)
        return {
            "engine": engine,
            "SessionLocal": TestSessionLocal,
            "upload_id": upload_id,
            "project_id": project_id,
        }

    return make


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_yt_service_with_videos_list(responses):
    """Build a fake yt_service whose .videos().list(...).execute() walks through
    `responses` in order. Each entry is either a dict (returned as-is) or an
    Exception (raised). After exhausting, the LAST response repeats."""
    state = {"i": 0}
    fake_yt = MagicMock(name="yt_service")

    def list_call(**_kwargs):
        idx = min(state["i"], len(responses) - 1)
        state["i"] += 1
        resp = responses[idx]
        req = MagicMock()
        if isinstance(resp, Exception):
            req.execute.side_effect = resp
        else:
            req.execute.return_value = resp
        return req

    videos_obj = MagicMock()
    videos_obj.list.side_effect = list_call
    fake_yt.videos.return_value = videos_obj
    return fake_yt


def _collect_callback():
    events = []

    async def callback(payload):
        events.append(payload)

    return events, callback


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_processing_polling_emits_start_progress_completed(db_factory):
    """Happy path: first poll says 'processing', second poll says 'processed'.
    We expect exactly one *_started, at least one *_progress, one *_completed."""
    db = db_factory()
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        {
            "items": [
                {
                    "status": {"uploadStatus": "uploaded"},
                    "processingDetails": {
                        "processingStatus": "processing",
                        "processingProgress": {"partsProcessed": 1, "partsTotal": 4},
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "status": {"uploadStatus": "processed"},
                    "processingDetails": {
                        "processingStatus": "succeeded",
                        "processingProgress": {"partsProcessed": 4, "partsTotal": 4},
                    },
                }
            ]
        },
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-stage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vid123", "youtube_url": "https://youtu.be/vid123"},
         ), \
         patch.object(um_module.quota_service, "record_usage"):

        async def _no_sleep(*_a, **_kw):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-stage"))

    types = [e["type"] for e in events]
    assert types.count("youtube_processing_started") == 1, types
    assert types.count("youtube_processing_progress") >= 1, types
    assert types.count("youtube_processing_completed") == 1, types

    # Order: started ... progress(s) ... completed
    started_idx = types.index("youtube_processing_started")
    completed_idx = types.index("youtube_processing_completed")
    assert started_idx < completed_idx
    progress_indices = [i for i, t in enumerate(types) if t == "youtube_processing_progress"]
    assert all(started_idx < pi < completed_idx for pi in progress_indices)

    # Sanity on payload: progress carries parts
    progress_events = [e for e in events if e["type"] == "youtube_processing_progress"]
    assert progress_events[0]["parts_total"] == 4
    assert progress_events[0]["parts_processed"] in (1, 4)

    # Completed event must report a final_status
    completed = [e for e in events if e["type"] == "youtube_processing_completed"][0]
    assert completed["final_status"] in ("succeeded", "processed")

    # Upload still ends 'completed'.
    session = db["SessionLocal"]()
    try:
        upload = session.query(Upload).filter(Upload.id == db["upload_id"]).first()
        assert upload.status == "completed"
        assert upload.youtube_video_id == "vid123"
    finally:
        session.close()


def test_processing_polling_exception_does_not_fail_upload(db_factory):
    """If videos().list().execute() raises, polling exits cleanly,
    youtube_processing_completed STILL fires, and the upload stays 'completed'."""
    db = db_factory()
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        RuntimeError("API exploded"),
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-stage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vid999", "youtube_url": "https://youtu.be/vid999"},
         ), \
         patch.object(um_module.quota_service, "record_usage"):

        async def _no_sleep(*_a, **_kw):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-stage"))

    types = [e["type"] for e in events]
    assert "youtube_processing_started" in types
    assert "youtube_processing_completed" in types, (
        "Completed event must fire even if polling threw"
    )

    session = db["SessionLocal"]()
    try:
        upload = session.query(Upload).filter(Upload.id == db["upload_id"]).first()
        assert upload.status == "completed", (
            "Polling failure must NOT fail the upload — the video is already on YouTube"
        )
        assert upload.youtube_video_id == "vid999"
    finally:
        session.close()


def test_thumbnail_applying_emitted_when_thumbnail_present(db_factory, tmp_path):
    """When upload.thumbnail_path is set, a thumbnail_applying event must fire
    BEFORE the thumbnail_set event."""
    thumb_file = tmp_path / "thumb.jpg"
    thumb_file.write_bytes(b"\xff\xd8\xff\xd9")  # tiny stub jpeg-ish
    db = db_factory(thumbnail_path=str(thumb_file))
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        {
            "items": [
                {
                    "status": {"uploadStatus": "processed"},
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-stage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidT", "youtube_url": "https://youtu.be/vidT"},
         ), \
         patch.object(um_module.youtube_service, "set_thumbnail", return_value=True), \
         patch("backend.services.upload_manager.compress_thumbnail", return_value=None), \
         patch.object(um_module.quota_service, "record_usage"):

        async def _no_sleep(*_a, **_kw):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-stage"))

    types = [e["type"] for e in events]
    assert "thumbnail_applying" in types, types
    assert types.index("thumbnail_applying") < types.index("thumbnail_set"), types


def test_thumbnail_applying_NOT_emitted_when_no_thumbnail(db_factory):
    """No thumbnail_path -> no thumbnail_applying event."""
    db = db_factory(thumbnail_path=None)
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        {
            "items": [
                {
                    "status": {"uploadStatus": "processed"},
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-stage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidNT", "youtube_url": "https://youtu.be/vidNT"},
         ), \
         patch.object(um_module.quota_service, "record_usage"):

        async def _no_sleep(*_a, **_kw):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-stage"))

    types = [e["type"] for e in events]
    assert "thumbnail_applying" not in types, (
        f"thumbnail_applying must not fire when thumbnail_path is None; got {types}"
    )
    assert "thumbnail_set" not in types


def test_comment_posting_emitted_when_default_comment_set(db_factory):
    db = db_factory(default_comment="Subscribe for more!")
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        {
            "items": [
                {
                    "status": {"uploadStatus": "processed"},
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-stage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidC", "youtube_url": "https://youtu.be/vidC"},
         ), \
         patch.object(um_module.youtube_service, "post_comment", return_value={"ok": True}), \
         patch.object(um_module.quota_service, "record_usage"):

        async def _no_sleep(*_a, **_kw):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-stage"))

    types = [e["type"] for e in events]
    assert "comment_posting" in types, types
    assert types.index("comment_posting") < types.index("comment_posted"), types


def test_comment_posting_NOT_emitted_when_default_comment_empty(db_factory):
    db = db_factory(default_comment="")
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        {
            "items": [
                {
                    "status": {"uploadStatus": "processed"},
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-stage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidNC", "youtube_url": "https://youtu.be/vidNC"},
         ), \
         patch.object(um_module.youtube_service, "post_comment") as mock_post, \
         patch.object(um_module.quota_service, "record_usage"):

        async def _no_sleep(*_a, **_kw):
            return None
        with patch.object(um_module.asyncio, "sleep", _no_sleep):
            _run(um_module.upload_manager.process_job("job-stage"))

    types = [e["type"] for e in events]
    assert "comment_posting" not in types, (
        f"comment_posting must not fire when default_comment is empty; got {types}"
    )
    assert "comment_posted" not in types
    mock_post.assert_not_called()
