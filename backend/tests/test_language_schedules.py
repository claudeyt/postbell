"""Tests for per-language posting schedules + per-channel override + resolve.

What we pin here:

* PUT /api/language-schedules/{lang} upserts (insert and update via the same
  endpoint), with HH:MM validation (00:00-23:59).
* GET /api/language-schedules lists rows in language_code order.
* DELETE /api/language-schedules/{lang} returns 204 and removes the row.
* Channel PATCH accepts custom_schedule_time and exposes it on responses.
* POST /api/uploads/resolve-schedule honours channel override, then language
  schedule, otherwise reports source='none' with an error mentioning the
  language code.
* already_passed is derived from a deterministic now (via the _now param) and
  scheduled_at_utc equals scheduled_at_brt + 3h (BRT is UTC-3 fixed).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models.account import Account
from backend.models.channel import Channel
from backend.models.channel_group import ChannelGroup  # noqa: F401 -- table creation
from backend.models.language_schedule import LanguageSchedule  # noqa: F401 -- table creation
from backend.models.project import Project
from backend.models.quota import QuotaUsage  # noqa: F401 -- table creation
from backend.models.upload import Upload  # noqa: F401 -- table creation


BRT = ZoneInfo("America/Sao_Paulo")


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'lang_sched_test.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
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


def _seed_channel(client, *, name="Chan A", channel_id="UC-A", language_code="pt"):
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        project = Project(
            name=f"P-{name}",
            client_secret_path=f"/fake/{name}.json",
            daily_quota_limit=10000,
        )
        session.add(project)
        session.commit()

        account = Account(
            email=f"{name}@example.com",
            project_id=project.id,
            token_path=f"/fake/{name}-token.json",
        )
        session.add(account)
        session.commit()

        ch = Channel(
            account_id=account.id,
            channel_id=channel_id,
            channel_name=name,
            language_code=language_code,
        )
        session.add(ch)
        session.commit()
        return ch.id
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Language schedule CRUD
# ---------------------------------------------------------------------------


def test_upsert_and_list_language_schedule(client):
    r = client.put("/api/language-schedules/pt", json={"time_brt": "12:00"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["language_code"] == "pt"
    assert body["time_brt"] == "12:00"
    assert "updated_at" in body

    listed = client.get("/api/language-schedules").json()
    assert [row["language_code"] for row in listed] == ["pt"]
    assert listed[0]["time_brt"] == "12:00"


def test_put_same_lang_updates_existing_row(client):
    client.put("/api/language-schedules/pt", json={"time_brt": "12:00"})
    r = client.put("/api/language-schedules/pt", json={"time_brt": "13:00"})
    assert r.status_code == 200, r.text
    assert r.json()["time_brt"] == "13:00"

    listed = client.get("/api/language-schedules").json()
    pt_rows = [row for row in listed if row["language_code"] == "pt"]
    assert len(pt_rows) == 1
    assert pt_rows[0]["time_brt"] == "13:00"


def test_delete_language_schedule(client):
    client.put("/api/language-schedules/pt", json={"time_brt": "12:00"})
    r = client.delete("/api/language-schedules/pt")
    assert r.status_code == 204, r.text

    listed = client.get("/api/language-schedules").json()
    assert all(row["language_code"] != "pt" for row in listed)


def test_invalid_time_format_rejected(client):
    r1 = client.put("/api/language-schedules/pt", json={"time_brt": "25:00"})
    assert r1.status_code == 422, r1.text

    r2 = client.put("/api/language-schedules/pt", json={"time_brt": "12-00"})
    assert r2.status_code == 422, r2.text


# ---------------------------------------------------------------------------
# Channel custom_schedule_time
# ---------------------------------------------------------------------------


def test_channel_custom_schedule_time_persists(client):
    ch_id = _seed_channel(client, name="WithCustom", channel_id="UC-WC")
    r = client.patch(
        f"/api/channels/{ch_id}", json={"custom_schedule_time": "13:30"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["custom_schedule_time"] == "13:30"

    # Persists across fetch.
    channels = client.get("/api/channels").json()
    found = [c for c in channels if c["id"] == ch_id][0]
    assert found["custom_schedule_time"] == "13:30"


def test_channel_custom_schedule_time_rejects_bad_format(client):
    ch_id = _seed_channel(client, name="Reject", channel_id="UC-Rej")
    r = client.patch(
        f"/api/channels/{ch_id}", json={"custom_schedule_time": "99:99"}
    )
    assert r.status_code == 422, r.text


def test_channel_custom_schedule_time_cleared_with_null(client):
    ch_id = _seed_channel(client, name="Clear", channel_id="UC-Clr")
    client.patch(
        f"/api/channels/{ch_id}", json={"custom_schedule_time": "08:15"}
    )
    r = client.patch(
        f"/api/channels/{ch_id}", json={"custom_schedule_time": None}
    )
    assert r.status_code == 200, r.text
    assert r.json()["custom_schedule_time"] is None


# ---------------------------------------------------------------------------
# Resolve schedule
# ---------------------------------------------------------------------------


def test_resolve_uses_channel_override(client):
    ch_id = _seed_channel(client, name="Override", channel_id="UC-OV", language_code="pt")
    client.put("/api/language-schedules/pt", json={"time_brt": "12:00"})
    client.patch(f"/api/channels/{ch_id}", json={"custom_schedule_time": "13:30"})

    r = client.post(
        "/api/uploads/resolve-schedule", json={"channel_ids": [ch_id]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    row = body[0]
    assert row["resolved_time"] == "13:30"
    assert row["source"] == "channel"
    assert row["error"] is None


def test_resolve_falls_back_to_language_schedule(client):
    ch_id = _seed_channel(client, name="LangFallback", channel_id="UC-LF", language_code="pt")
    client.put("/api/language-schedules/pt", json={"time_brt": "10:30"})

    r = client.post(
        "/api/uploads/resolve-schedule", json={"channel_ids": [ch_id]}
    )
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["resolved_time"] == "10:30"
    assert row["source"] == "language"
    assert row["error"] is None


def test_resolve_no_schedule_reports_error_with_language_code(client):
    ch_id = _seed_channel(client, name="None", channel_id="UC-None", language_code="ko")

    r = client.post(
        "/api/uploads/resolve-schedule", json={"channel_ids": [ch_id]}
    )
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["resolved_time"] is None
    assert row["source"] == "none"
    assert row["error"] is not None
    assert "ko" in row["error"]


def test_resolve_already_passed_deterministic_via_now_patch(client, monkeypatch):
    """Patch _get_now_brt to a fixed time so we can assert already_passed both ways."""
    from backend.api import uploads as uploads_module

    ch_id = _seed_channel(client, name="Passed", channel_id="UC-PS", language_code="pt")
    client.put("/api/language-schedules/pt", json={"time_brt": "12:00"})

    # Case A: now > scheduled (15:00 BRT today) -> already_passed=True
    fake_late = datetime(2026, 6, 10, 15, 0, tzinfo=BRT)
    monkeypatch.setattr(uploads_module, "_get_now_brt", lambda: fake_late)
    r1 = client.post(
        "/api/uploads/resolve-schedule", json={"channel_ids": [ch_id]}
    )
    assert r1.status_code == 200, r1.text
    row1 = r1.json()[0]
    assert row1["resolved_time"] == "12:00"
    assert row1["already_passed"] is True

    # Case B: now < scheduled (08:00 BRT today) -> already_passed=False
    fake_early = datetime(2026, 6, 10, 8, 0, tzinfo=BRT)
    monkeypatch.setattr(uploads_module, "_get_now_brt", lambda: fake_early)
    r2 = client.post(
        "/api/uploads/resolve-schedule", json={"channel_ids": [ch_id]}
    )
    assert r2.status_code == 200, r2.text
    row2 = r2.json()[0]
    assert row2["already_passed"] is False


def test_resolve_scheduled_at_utc_matches_brt_conversion(client, monkeypatch):
    """A scheduled time of 12:00 BRT on 2026-06-10 must be 15:00 UTC same day."""
    from backend.api import uploads as uploads_module

    ch_id = _seed_channel(client, name="UTC", channel_id="UC-UTC", language_code="pt")
    client.put("/api/language-schedules/pt", json={"time_brt": "12:00"})

    fake_now = datetime(2026, 6, 10, 9, 0, tzinfo=BRT)
    monkeypatch.setattr(uploads_module, "_get_now_brt", lambda: fake_now)

    r = client.post(
        "/api/uploads/resolve-schedule", json={"channel_ids": [ch_id]}
    )
    assert r.status_code == 200, r.text
    row = r.json()[0]

    # scheduled_at_brt is 2026-06-10 12:00 BRT (-03:00); scheduled_at_utc is the
    # same instant expressed as UTC = 2026-06-10 15:00 UTC.
    brt_dt = datetime.fromisoformat(row["scheduled_at_brt"])
    utc_dt = datetime.fromisoformat(row["scheduled_at_utc"])
    assert brt_dt.utcoffset().total_seconds() == -3 * 3600
    assert utc_dt.year == 2026 and utc_dt.month == 6 and utc_dt.day == 10
    assert utc_dt.hour == 15 and utc_dt.minute == 0
    # And they must refer to the same instant.
    assert brt_dt.astimezone(ZoneInfo("UTC")) == utc_dt.astimezone(ZoneInfo("UTC"))


def test_resolve_target_date_in_future_never_already_passed(client, monkeypatch):
    """target_date in the future combined with a time-of-day that has already
    passed today must NOT be flagged as already_passed; the scheduled date
    matches the requested target_date.
    """
    from backend.api import uploads as uploads_module

    ch_id = _seed_channel(client, name="FutureDate", channel_id="UC-FD", language_code="pt")
    # PT schedule = 08:00 (long past by mid-afternoon today).
    client.put("/api/language-schedules/pt", json={"time_brt": "08:00"})

    fake_now = datetime(2026, 6, 10, 15, 0, tzinfo=BRT)  # 15:00 BRT today
    monkeypatch.setattr(uploads_module, "_get_now_brt", lambda: fake_now)

    tomorrow = (fake_now + timedelta(days=1)).date().isoformat()
    r = client.post(
        "/api/uploads/resolve-schedule",
        json={"channel_ids": [ch_id], "target_date": tomorrow},
    )
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["resolved_time"] == "08:00"
    assert row["already_passed"] is False
    brt_dt = datetime.fromisoformat(row["scheduled_at_brt"])
    assert brt_dt.date().isoformat() == tomorrow
    assert brt_dt.hour == 8 and brt_dt.minute == 0


def test_resolve_target_date_today_with_future_time_not_passed(client, monkeypatch):
    """target_date=today with a time-of-day still ahead -> not already_passed."""
    from backend.api import uploads as uploads_module

    ch_id = _seed_channel(client, name="TodayFuture", channel_id="UC-TF", language_code="pt")
    # PT schedule = (now + 1h) = 10:00 BRT.
    client.put("/api/language-schedules/pt", json={"time_brt": "10:00"})

    fake_now = datetime(2026, 6, 10, 9, 0, tzinfo=BRT)
    monkeypatch.setattr(uploads_module, "_get_now_brt", lambda: fake_now)

    today = fake_now.date().isoformat()
    r = client.post(
        "/api/uploads/resolve-schedule",
        json={"channel_ids": [ch_id], "target_date": today},
    )
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["resolved_time"] == "10:00"
    assert row["already_passed"] is False
    brt_dt = datetime.fromisoformat(row["scheduled_at_brt"])
    assert brt_dt.date().isoformat() == today


def test_resolve_target_date_in_past_already_passed(client, monkeypatch):
    """target_date in the past must always be already_passed regardless of time."""
    from backend.api import uploads as uploads_module

    ch_id = _seed_channel(client, name="PastDate", channel_id="UC-PD", language_code="pt")
    client.put("/api/language-schedules/pt", json={"time_brt": "23:00"})

    fake_now = datetime(2026, 6, 10, 9, 0, tzinfo=BRT)
    monkeypatch.setattr(uploads_module, "_get_now_brt", lambda: fake_now)

    yesterday = (fake_now - timedelta(days=1)).date().isoformat()
    r = client.post(
        "/api/uploads/resolve-schedule",
        json={"channel_ids": [ch_id], "target_date": yesterday},
    )
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["resolved_time"] == "23:00"
    assert row["already_passed"] is True
    brt_dt = datetime.fromisoformat(row["scheduled_at_brt"])
    assert brt_dt.date().isoformat() == yesterday


def test_resolve_missing_channel_returns_error(client):
    r = client.post(
        "/api/uploads/resolve-schedule", json={"channel_ids": [99999]}
    )
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["channel_id"] == 99999
    assert row["error"] == "Channel not found"
    assert row["resolved_time"] is None
    assert row["source"] == "none"
