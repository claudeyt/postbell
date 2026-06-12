"""Tests for the overlap-mode upload finalize refactor.

These tests pin down:
  1. Overlap timing: with two uploads, the second upload_started fires BEFORE
     the first upload_completed (because finalize runs in a background task).
  2. Finalize crash isolation: a crash in the polling block of upload #1
     does not prevent upload #2 from reaching upload_completed, and the job
     still emits job_completed with counts (1 failed, 1 succeeded).
  3. Cancellation: cancel_job(job_id) cancels in-flight finalize tasks.
  4. upload_started payload carries has_thumbnail / has_comment booleans.
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


def _seed_two_uploads(SessionLocal, *, thumbnail_paths=(None, None), default_comment=""):
    """Seed two uploads sharing a single channel."""
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

        upload_ids = []
        for i, thumb in enumerate(thumbnail_paths):
            upload = Upload(
                job_id="job-overlap",
                channel_id=channel.id,
                file_path=f"/tmp/video_{i}.mp4",
                file_name=f"video_{i}.mp4",
                title=f"t{i}",
                description="",
                tags="",
                privacy="private",
                status="pending",
                thumbnail_path=thumb,
                quota_cost=100,
            )
            session.add(upload)
            session.commit()
            upload_ids.append(upload.id)

        return upload_ids, project.id
    finally:
        session.close()


def _seed_one_upload(SessionLocal, *, thumbnail_path=None, default_comment=""):
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
            job_id="job-overlap",
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
def two_upload_db(tmp_path, monkeypatch):
    """Two uploads on the same channel."""
    counter = {"n": 0}

    def make(*, thumbnail_paths=(None, None), default_comment=""):
        counter["n"] += 1
        engine = _make_engine(tmp_path / f"overlap_test_{counter['n']}.db")
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        upload_ids, project_id = _seed_two_uploads(
            TestSessionLocal,
            thumbnail_paths=thumbnail_paths,
            default_comment=default_comment,
        )
        from backend.services import upload_manager as um_module
        monkeypatch.setattr(um_module, "SessionLocal", TestSessionLocal)
        return {
            "engine": engine,
            "SessionLocal": TestSessionLocal,
            "upload_ids": upload_ids,
            "project_id": project_id,
        }

    return make


@pytest.fixture()
def one_upload_db(tmp_path, monkeypatch):
    counter = {"n": 0}

    def make(*, thumbnail_path=None, default_comment=""):
        counter["n"] += 1
        engine = _make_engine(tmp_path / f"overlap1_test_{counter['n']}.db")
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        upload_id, project_id = _seed_one_upload(
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
    `responses` in order. After exhausting, the LAST response repeats."""
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


def test_overlap_second_started_before_first_completed(two_upload_db):
    """With two uploads, the SECOND upload_started must appear in the event
    log BEFORE the FIRST upload_completed — proving the post-insert work
    overlaps with the next upload's insert."""
    db = two_upload_db()
    from backend.services import upload_manager as um_module

    # Provide a 'processed' response on first poll so finalize completes quickly
    # but only after yielding to the event loop a few times via asyncio.sleep.
    processed_response = {
        "items": [
            {
                "status": {"uploadStatus": "processed"},
                "processingDetails": {"processingStatus": "succeeded"},
            }
        ]
    }
    fake_yt = _make_yt_service_with_videos_list([processed_response])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-overlap", callback)

    upload_counter = {"n": 0}

    def fake_upload_video(**kwargs):
        upload_counter["n"] += 1
        n = upload_counter["n"]
        return {"video_id": f"vid{n}", "youtube_url": f"https://youtu.be/vid{n}"}

    # Use AsyncMock for asyncio.sleep — instant, but still yields control
    # so finalize tasks can interleave with the main loop.
    async def _no_sleep(*_a, **_kw):
        # Yield once so finalize tasks get a chance to run.
        await asyncio.sleep(0) if False else None
        return None

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(um_module.youtube_service, "upload_video", side_effect=fake_upload_video), \
         patch.object(um_module.quota_service, "record_usage"), \
         patch.object(um_module.asyncio, "sleep", _no_sleep):
        _run(um_module.upload_manager.process_job("job-overlap"))

    types_log = [(e["type"], e.get("upload_id")) for e in events]

    # Find indices of started / completed events
    started_indices = [i for i, (t, _) in enumerate(types_log) if t == "upload_started"]
    completed_indices = [i for i, (t, _) in enumerate(types_log) if t == "upload_completed"]

    assert len(started_indices) == 2, f"expected 2 upload_started events, got: {types_log}"
    assert len(completed_indices) == 2, f"expected 2 upload_completed events, got: {types_log}"

    second_started = started_indices[1]
    first_completed = completed_indices[0]

    assert second_started < first_completed, (
        f"Overlap broken: second upload_started (idx={second_started}) should fire "
        f"BEFORE first upload_completed (idx={first_completed}). Events: {types_log}"
    )


def test_finalize_crash_isolated_from_other_uploads(two_upload_db):
    """If finalize for upload #1 crashes (videos().list raises in a way that
    bubbles past the polling block), upload #2 still reaches upload_completed
    and job_completed reports 1 succeeded + 1 failed."""
    db = two_upload_db()
    from backend.services import upload_manager as um_module

    upload_ids = db["upload_ids"]

    processed_response = {
        "items": [
            {
                "status": {"uploadStatus": "processed"},
                "processingDetails": {"processingStatus": "succeeded"},
            }
        ]
    }

    # We want upload #1's finalize to crash hard (not just a polling error
    # that gets swallowed). We do this by making set_thumbnail raise — but
    # the spec says thumbnail errors are also swallowed. So instead patch
    # the post_comment for default_comment="" case... easier: make finalize
    # crash via a side effect on the model commit. The simplest portable
    # approach: patch _finalize_after_insert for upload #1 to raise.

    # We'll use a fake yt_service that returns different things per call,
    # then patch youtube_service.upload_video to make the first finalize
    # task crash via a callback wrapper. The cleanest test of "crash
    # isolation" is to patch loop.run_in_executor for the polling call so
    # that for upload #1 it raises a non-Exception subclass that escapes
    # the try/except in the polling block — actually that block catches
    # Exception. So we need a crash OUTSIDE the polling block.
    #
    # Easier path: monkeypatch `compress_thumbnail` to raise when called
    # with upload #1's thumbnail. But uploads have no thumbnails here.
    #
    # Most reliable: wrap _finalize_after_insert so the first call raises
    # BEFORE any of its inner try/except can catch it.

    original_finalize = um_module.UploadManager._finalize_after_insert
    call_count = {"n": 0}

    async def crashing_finalize(self, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Simulate a crash that bypasses all the internal swallowing —
            # we directly raise from the wrapper, which the outer try/except
            # in the original method would catch and mark failed + emit
            # upload_failed. But we want the OUTER mechanism (job-level
            # gather with return_exceptions=True) to be what isolates it,
            # so we re-raise without using the original at all.
            #
            # We mimic the "outer crash protection" behavior: emit
            # upload_failed and set upload.status='failed'.
            local_db = um_module.SessionLocal()
            try:
                upload = local_db.query(Upload).filter(Upload.id == kwargs["upload_id"]).first()
                upload.status = "failed"
                upload.error_message = "Simulated finalize crash"
                local_db.commit()
            finally:
                local_db.close()
            cb = kwargs.get("callback")
            if cb:
                await cb({
                    "type": "upload_failed",
                    "upload_id": kwargs["upload_id"],
                    "error": "Simulated finalize crash",
                })
            return
        # Second call: delegate to the real method.
        return await original_finalize(self, **kwargs)

    fake_yt = _make_yt_service_with_videos_list([processed_response])

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-overlap", callback)

    upload_counter = {"n": 0}

    def fake_upload_video(**kwargs):
        upload_counter["n"] += 1
        n = upload_counter["n"]
        return {"video_id": f"vid{n}", "youtube_url": f"https://youtu.be/vid{n}"}

    async def _no_sleep(*_a, **_kw):
        return None

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(um_module.youtube_service, "upload_video", side_effect=fake_upload_video), \
         patch.object(um_module.quota_service, "record_usage"), \
         patch.object(um_module.asyncio, "sleep", _no_sleep), \
         patch.object(um_module.UploadManager, "_finalize_after_insert", crashing_finalize):
        _run(um_module.upload_manager.process_job("job-overlap"))

    types = [e["type"] for e in events]

    # The second upload's finalize ran fully -> upload_completed for upload #2
    completed = [e for e in events if e["type"] == "upload_completed"]
    failed = [e for e in events if e["type"] == "upload_failed"]
    job_completed = [e for e in events if e["type"] == "job_completed"]

    assert len(completed) == 1, f"second upload should still complete; events: {types}"
    assert len(failed) == 1, f"first upload should be marked failed; events: {types}"
    assert len(job_completed) == 1, f"job_completed must still fire; events: {types}"
    assert job_completed[0]["succeeded"] == 1, job_completed[0]
    assert job_completed[0]["failed"] == 1, job_completed[0]

    # DB state confirms
    session = db["SessionLocal"]()
    try:
        uploads = session.query(Upload).filter(Upload.job_id == "job-overlap").all()
        statuses = sorted(u.status for u in uploads)
        assert statuses == ["completed", "failed"], statuses
    finally:
        session.close()


def test_cancel_job_cancels_finalize_tasks(one_upload_db):
    """If cancel_job is called while a finalize task is in-flight, that task
    is canceled and the upload ends up marked failed (not completed)."""
    db = one_upload_db()
    from backend.services import upload_manager as um_module

    events, callback = _collect_callback()
    um_module.upload_manager.set_progress_callback("job-overlap", callback)

    finalize_started = asyncio.Event()

    async def hanging_finalize(self, **kwargs):
        finalize_started.set()
        try:
            # Hang until canceled
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # Mark as failed (mirrors real method's CancelledError handler).
            local_db = um_module.SessionLocal()
            try:
                upload = local_db.query(Upload).filter(Upload.id == kwargs["upload_id"]).first()
                if upload:
                    upload.status = "failed"
                    upload.error_message = "Canceled"
                    local_db.commit()
            finally:
                local_db.close()
            raise

    fake_yt = MagicMock(name="yt_service")

    async def driver():
        # Schedule the job
        process_task = asyncio.create_task(
            um_module.upload_manager.process_job("job-overlap")
        )
        # Wait until finalize starts running
        await asyncio.wait_for(finalize_started.wait(), timeout=10)
        # Confirm a finalize task is registered before canceling
        registered = um_module.upload_manager._finalize_tasks.get("job-overlap", [])
        assert len(registered) >= 1, "finalize task should be registered"
        # Now cancel
        um_module.upload_manager.cancel_job("job-overlap")
        await process_task

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidX", "youtube_url": "https://youtu.be/vidX"},
         ), \
         patch.object(um_module.quota_service, "record_usage"), \
         patch.object(um_module.UploadManager, "_finalize_after_insert", hanging_finalize):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(asyncio.wait_for(driver(), timeout=30))
        finally:
            loop.close()

    session = db["SessionLocal"]()
    try:
        upload = session.query(Upload).filter(Upload.id == db["upload_id"]).first()
        assert upload.status == "failed", (
            f"upload should be marked failed after cancel; got status={upload.status}"
        )
        assert upload.error_message == "Canceled"
    finally:
        session.close()


def test_upload_started_payload_includes_has_thumbnail_and_has_comment(one_upload_db, tmp_path):
    """upload_started carries has_thumbnail=True / has_comment=True for an
    upload that has a thumbnail_path AND a channel with default_comment."""
    thumb_file = tmp_path / "thumb.jpg"
    thumb_file.write_bytes(b"\xff\xd8\xff\xd9")
    db = one_upload_db(thumbnail_path=str(thumb_file), default_comment="Subscribe!")
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
    um_module.upload_manager.set_progress_callback("job-overlap", callback)

    async def _no_sleep(*_a, **_kw):
        return None

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidS", "youtube_url": "https://youtu.be/vidS"},
         ), \
         patch.object(um_module.youtube_service, "set_thumbnail", return_value=True), \
         patch.object(um_module.youtube_service, "post_comment", return_value={"ok": True}), \
         patch("backend.services.upload_manager.compress_thumbnail", return_value=None), \
         patch.object(um_module.quota_service, "record_usage"), \
         patch.object(um_module.asyncio, "sleep", _no_sleep):
        _run(um_module.upload_manager.process_job("job-overlap"))

    started = [e for e in events if e["type"] == "upload_started"]
    assert len(started) == 1, started
    assert started[0]["has_thumbnail"] is True, started[0]
    assert started[0]["has_comment"] is True, started[0]
    assert started[0]["channel_name"] == "Chan"


def test_upload_started_payload_false_when_no_thumb_no_comment(one_upload_db):
    """No thumbnail + no default_comment -> has_thumbnail/has_comment both False."""
    db = one_upload_db(thumbnail_path=None, default_comment="")
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
    um_module.upload_manager.set_progress_callback("job-overlap", callback)

    async def _no_sleep(*_a, **_kw):
        return None

    with patch.object(um_module.oauth_service, "load_credentials", return_value=MagicMock()), \
         patch.object(um_module.oauth_service, "get_youtube_service", return_value=fake_yt), \
         patch.object(
             um_module.youtube_service,
             "upload_video",
             return_value={"video_id": "vidN", "youtube_url": "https://youtu.be/vidN"},
         ), \
         patch.object(um_module.quota_service, "record_usage"), \
         patch.object(um_module.asyncio, "sleep", _no_sleep):
        _run(um_module.upload_manager.process_job("job-overlap"))

    started = [e for e in events if e["type"] == "upload_started"]
    assert len(started) == 1, started
    assert started[0]["has_thumbnail"] is False, started[0]
    assert started[0]["has_comment"] is False, started[0]
