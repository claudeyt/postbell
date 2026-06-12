"""Tests for the per-project ``videos_today`` / ``video_limit`` counter added
to ``/api/quota/summary``.

What we pin here:

* ``videos_today`` counts Upload rows whose channel's account belongs to the
  project AND whose ``created_at`` lands inside the current Pacific calendar
  day (because YouTube resets at midnight America/Los_Angeles).
* Uploads created on the *previous* Pacific calendar day are NOT counted.
* ``video_limit`` is the hardcoded module constant (currently 100).
* A project with zero uploads reports ``videos_today=0``.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.project import Project
from backend.models.account import Account
from backend.models.channel import Channel
from backend.models.upload import Upload
from backend.models.quota import QuotaUsage  # noqa: F401 -- needed for table creation
from backend.services import quota_service as quota_service_module
from backend.services.quota_service import (
    DAILY_VIDEO_LIMIT,
    PACIFIC_TZ,
    quota_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path):
    """Fresh per-test SQLite DB; never touches data/postbell.db."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'quota_video_test.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_project_with_channel(session, *, project_name: str):
    """Create Project -> Account -> Channel; return (project_id, channel_id)."""
    project = Project(
        name=project_name,
        client_secret_path=f"/fake/{project_name}.json",
        daily_quota_limit=10000,
    )
    session.add(project)
    session.commit()

    account = Account(
        email=f"{project_name}@example.com",
        project_id=project.id,
        token_path=f"/fake/{project_name}-token.json",
    )
    session.add(account)
    session.commit()

    channel = Channel(
        account_id=account.id,
        channel_id=f"UC-{project_name}",
        channel_name=f"Chan {project_name}",
        language_code="en",
    )
    session.add(channel)
    session.commit()
    return project.id, channel.id


def _utc_naive_for_pacific(pacific_dt: datetime) -> datetime:
    """Convert a Pacific-aware datetime to the naive-UTC value SQLAlchemy stores
    in ``Upload.created_at`` (the model uses ``default=datetime.utcnow``).
    """
    return pacific_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _make_upload(session, channel_id: int, *, created_at: datetime, suffix: str):
    upload = Upload(
        job_id=f"job-{suffix}",
        channel_id=channel_id,
        file_path=f"/tmp/{suffix}.mp4",
        file_name=f"{suffix}.mp4",
        title=f"t-{suffix}",
        description="",
        tags="",
        privacy="private",
        status="pending",
        quota_cost=100,
        created_at=created_at,
    )
    session.add(upload)
    session.commit()
    return upload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_videos_today_counts_uploads_created_today_pacific(db_session, monkeypatch):
    """Upload rows created today (Pacific) AND linked to the project via
    Channel -> Account must appear in ``videos_today``.
    """
    # Pin "today" so the test is deterministic regardless of when it runs.
    fake_today_pacific = datetime(2026, 6, 5, 14, 0, 0, tzinfo=PACIFIC_TZ)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return fake_today_pacific.replace(tzinfo=None)
            return fake_today_pacific.astimezone(tz)

    monkeypatch.setattr(quota_service_module, "datetime", _FakeDateTime)

    project_id, channel_id = _seed_project_with_channel(db_session, project_name="P1")

    # Three uploads spread across today (Pacific): early morning, mid, late evening.
    today_pacific_date = fake_today_pacific.date()
    for hour, suffix in [(0, "morning"), (12, "noon"), (23, "evening")]:
        pacific_dt = datetime.combine(
            today_pacific_date, time(hour=hour, minute=30), tzinfo=PACIFIC_TZ
        )
        _make_upload(
            db_session,
            channel_id,
            created_at=_utc_naive_for_pacific(pacific_dt),
            suffix=suffix,
        )

    summary = quota_service.get_summary(db_session)
    assert len(summary) == 1
    item = summary[0]
    assert item.project_id == project_id
    assert item.videos_today == 3, f"expected 3 uploads today, got {item.videos_today}"


def test_videos_today_excludes_uploads_from_yesterday_pacific(db_session, monkeypatch):
    """An upload created at 23:30 *yesterday* Pacific must NOT count -- even if
    it's still "today" in UTC."""
    fake_today_pacific = datetime(2026, 6, 5, 10, 0, 0, tzinfo=PACIFIC_TZ)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return fake_today_pacific.replace(tzinfo=None)
            return fake_today_pacific.astimezone(tz)

    monkeypatch.setattr(quota_service_module, "datetime", _FakeDateTime)

    _project_id, channel_id = _seed_project_with_channel(db_session, project_name="P1")

    yesterday_pacific = fake_today_pacific.date() - timedelta(days=1)
    yesterday_late = datetime.combine(
        yesterday_pacific, time(hour=23, minute=30), tzinfo=PACIFIC_TZ
    )
    today_morning = datetime.combine(
        fake_today_pacific.date(), time(hour=1, minute=0), tzinfo=PACIFIC_TZ
    )

    _make_upload(
        db_session,
        channel_id,
        created_at=_utc_naive_for_pacific(yesterday_late),
        suffix="yesterday",
    )
    _make_upload(
        db_session,
        channel_id,
        created_at=_utc_naive_for_pacific(today_morning),
        suffix="today",
    )

    summary = quota_service.get_summary(db_session)
    assert summary[0].videos_today == 1, (
        f"only the today-Pacific upload should count, got {summary[0].videos_today}"
    )


def test_summary_reports_hardcoded_video_limit(db_session):
    """``video_limit`` mirrors the module constant (currently 100)."""
    _seed_project_with_channel(db_session, project_name="P1")
    summary = quota_service.get_summary(db_session)
    assert summary[0].video_limit == DAILY_VIDEO_LIMIT == 100


def test_project_with_no_uploads_reports_zero(db_session):
    """A freshly-created project with no Upload rows must return
    ``videos_today=0`` (not None, not an error)."""
    _seed_project_with_channel(db_session, project_name="Empty")
    summary = quota_service.get_summary(db_session)
    assert len(summary) == 1
    assert summary[0].videos_today == 0
    assert summary[0].video_limit == 100
