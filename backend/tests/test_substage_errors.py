"""Tests for sub-stage failure events.

When a sub-stage (YouTube verification, thumbnail apply, comment post) fails,
UploadManager._finalize_after_insert must:

1. Emit a *_failed event with the error message.
2. NOT emit the corresponding success event (thumbnail_set / comment_posted).
3. STILL finish the upload as 'completed' (video is already on YouTube).
4. STILL fire the final upload_completed callback.

The verification block additionally still emits youtube_processing_completed
after verification_failed (existing behavior preserved).
"""
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

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
# Helpers (mirror test_upload_stage_events.py style)
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
            job_id="job-substage",
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
    counter = {"n": 0}

    def make(*, thumbnail_path=None, default_comment=""):
        counter["n"] += 1
        engine = _make_engine(tmp_path / f"substage_test_{counter['n']}.db")
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


def _assert_completed(db):
    """The upload row must end as 'completed' regardless of sub-stage failures."""
    session = db["SessionLocal"]()
    try:
        upload = session.query(Upload).filter(Upload.id == db["upload_id"]).first()
        assert upload is not None, "upload row vanished"
        assert upload.status == "completed", (
            f"upload.status must remain 'completed' even when a sub-stage fails (got {upload.status!r})"
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_verification_failed_when_youtube_reports_rejected(db_factory):
    """uploadStatus='rejected' on first poll: verification_failed must fire
    BEFORE youtube_processing_completed, but upload still completes."""
    db = db_factory()
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        {
            "items": [
                {
                    "status": {"uploadStatus": "rejected"},
                    "processingDetails": {},
                }
            ]
        }
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-substage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidR", "youtube_url": "https://youtu.be/vidR"},
         ), \
         patch.object(um_module.quota_service, "record_usage"):

        with patch.object(um_module.asyncio, "sleep", new=AsyncMock(return_value=None)):
            _run(um_module.upload_manager.process_job("job-substage"))

    types = [e["type"] for e in events]
    assert "verification_failed" in types, f"verification_failed missing; got {types}"

    verif_failed = [e for e in events if e["type"] == "verification_failed"][0]
    assert verif_failed["error"] in ("rejected", "failed", "terminated"), verif_failed
    # verification_failed must precede youtube_processing_completed
    assert types.index("verification_failed") < types.index("youtube_processing_completed"), types
    # upload_completed still fires
    assert "upload_completed" in types, types

    _assert_completed(db)


def test_thumbnail_failed_when_set_thumbnail_raises(db_factory, tmp_path):
    """set_thumbnail raises -> thumbnail_failed fires, no thumbnail_set,
    upload still completes."""
    thumb_file = tmp_path / "thumb.jpg"
    thumb_file.write_bytes(b"\xff\xd8\xff\xd9")
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
    um_module.upload_manager.set_progress_callback("job-substage", callback)

    boom = RuntimeError("thumbnail API down")

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidTE", "youtube_url": "https://youtu.be/vidTE"},
         ), \
         patch.object(um_module.youtube_service, "set_thumbnail", side_effect=boom), \
         patch("backend.services.upload_manager.compress_thumbnail", return_value=None), \
         patch.object(um_module.quota_service, "record_usage"):

        with patch.object(um_module.asyncio, "sleep", new=AsyncMock(return_value=None)):
            _run(um_module.upload_manager.process_job("job-substage"))

    types = [e["type"] for e in events]
    assert "thumbnail_failed" in types, f"thumbnail_failed missing; got {types}"
    assert "thumbnail_set" not in types, (
        f"thumbnail_set must NOT fire when set_thumbnail raised; got {types}"
    )

    thumb_failed = [e for e in events if e["type"] == "thumbnail_failed"][0]
    assert "thumbnail API down" in thumb_failed["error"], thumb_failed

    assert "upload_completed" in types
    _assert_completed(db)


def test_thumbnail_failed_when_set_thumbnail_returns_false(db_factory, tmp_path):
    """set_thumbnail returns False -> thumbnail_failed with the standard message,
    no thumbnail_set, upload still completes."""
    thumb_file = tmp_path / "thumb.jpg"
    thumb_file.write_bytes(b"\xff\xd8\xff\xd9")
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
    um_module.upload_manager.set_progress_callback("job-substage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidTF", "youtube_url": "https://youtu.be/vidTF"},
         ), \
         patch.object(um_module.youtube_service, "set_thumbnail", return_value=False), \
         patch("backend.services.upload_manager.compress_thumbnail", return_value=None), \
         patch.object(um_module.quota_service, "record_usage"):

        with patch.object(um_module.asyncio, "sleep", new=AsyncMock(return_value=None)):
            _run(um_module.upload_manager.process_job("job-substage"))

    types = [e["type"] for e in events]
    assert "thumbnail_failed" in types, f"thumbnail_failed missing; got {types}"
    assert "thumbnail_set" not in types, types

    thumb_failed = [e for e in events if e["type"] == "thumbnail_failed"][0]
    assert thumb_failed["error"] == "Thumbnail upload returned failure", thumb_failed

    assert "upload_completed" in types
    _assert_completed(db)


def test_verification_failed_when_polling_raises(db_factory):
    """videos.list().execute() raises Exception on first poll:
    verification_failed must fire with 'polling error:' prefix BEFORE
    youtube_processing_completed, and upload still completes."""
    db = db_factory()
    from backend.services import upload_manager as um_module

    fake_yt = _make_yt_service_with_videos_list([
        Exception("network down"),
    ])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-substage", callback)

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidPE", "youtube_url": "https://youtu.be/vidPE"},
         ), \
         patch.object(um_module.quota_service, "record_usage"):

        with patch.object(um_module.asyncio, "sleep", new=AsyncMock(return_value=None)):
            _run(um_module.upload_manager.process_job("job-substage"))

    types = [e["type"] for e in events]
    assert "verification_failed" in types, f"verification_failed missing; got {types}"

    verif_failed = [e for e in events if e["type"] == "verification_failed"][0]
    assert "network down" in verif_failed["error"], verif_failed
    assert verif_failed["error"].startswith("polling error:"), verif_failed

    # verification_failed must precede youtube_processing_completed
    assert "youtube_processing_completed" in types, types
    assert types.index("verification_failed") < types.index("youtube_processing_completed"), types

    # upload_completed still fires and row is completed
    assert "upload_completed" in types, types
    _assert_completed(db)


def test_comment_failed_when_post_comment_raises(db_factory):
    """post_comment raises -> comment_failed fires, no comment_posted,
    upload still completes."""
    db = db_factory(default_comment="Subscribe!")
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
    um_module.upload_manager.set_progress_callback("job-substage", callback)

    boom = RuntimeError("comments disabled")

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidCE", "youtube_url": "https://youtu.be/vidCE"},
         ), \
         patch.object(um_module.youtube_service, "post_comment", side_effect=boom), \
         patch.object(um_module.quota_service, "record_usage"):

        with patch.object(um_module.asyncio, "sleep", new=AsyncMock(return_value=None)):
            _run(um_module.upload_manager.process_job("job-substage"))

    types = [e["type"] for e in events]
    assert "comment_failed" in types, f"comment_failed missing; got {types}"
    assert "comment_posted" not in types, (
        f"comment_posted must NOT fire when post_comment raised; got {types}"
    )

    comment_failed = [e for e in events if e["type"] == "comment_failed"][0]
    assert "comments disabled" in comment_failed["error"], comment_failed

    assert "upload_completed" in types
    _assert_completed(db)
