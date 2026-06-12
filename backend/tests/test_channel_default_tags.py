"""Tests for the channel default_tags feature.

Pins:
* PATCH /api/channels/{id} with default_tags persists and is returned by GET.
* upload_manager.create_job falls back to channel.default_tags when the
  job-level `tags` argument is empty; the resulting Upload row carries the
  channel's default_tags string.
* POST /api/channels/{id}/pull-youtube-tags fetches brandingSettings.keywords,
  shlex-splits it into a comma-separated string, and persists it. YouTube call
  is fully mocked — no network.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models.account import Account
from backend.models.channel import Channel
from backend.models.channel_group import ChannelGroup  # noqa: F401
from backend.models.project import Project
from backend.models.quota import QuotaUsage  # noqa: F401
from backend.models.upload import Upload  # noqa: F401
from backend.services.upload_manager import UploadManager


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'default_tags_test.db'}",
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


def _seed_channel(client, *, name="Chan", channel_id="UC-A"):
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
            language_code="en",
        )
        session.add(ch)
        session.commit()
        return ch.id
    finally:
        session.close()


def test_patch_channel_default_tags_persists(client):
    ch_id = _seed_channel(client, name="Tagger", channel_id="UC-Tag")

    r = client.patch(f"/api/channels/{ch_id}", json={"default_tags": "a, b, c"})
    assert r.status_code == 200, r.text
    assert r.json()["default_tags"] == "a, b, c"

    channels = client.get("/api/channels").json()
    found = [c for c in channels if c["id"] == ch_id][0]
    assert found["default_tags"] == "a, b, c"


def test_patch_channel_default_tags_can_be_cleared(client):
    ch_id = _seed_channel(client, name="Clearer", channel_id="UC-Clear")
    client.patch(f"/api/channels/{ch_id}", json={"default_tags": "x, y"})
    r = client.patch(f"/api/channels/{ch_id}", json={"default_tags": None})
    assert r.status_code == 200, r.text
    assert r.json()["default_tags"] is None


def test_upload_manager_falls_back_to_channel_default_tags(client):
    """When job-level `tags` is empty, the Upload row uses channel.default_tags."""
    ch_id = _seed_channel(client, name="Fallback", channel_id="UC-Fall")
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        ch = session.query(Channel).filter(Channel.id == ch_id).first()
        ch.default_tags = "x, y"
        session.commit()

        mgr = UploadManager()
        job_id = mgr.create_job(
            routing=[
                {
                    "channel_id": ch_id,
                    "file_path": "/tmp/fake.mp4",
                    "file_name": "fake.mp4",
                }
            ],
            thumbnail_path=None,
            privacy="private",
            description="some desc",
            tags="",  # empty -> should fall back
            scheduled_at=None,
            db=session,
        )
        uploads = session.query(Upload).filter(Upload.job_id == job_id).all()
        assert len(uploads) == 1
        assert uploads[0].tags == "x, y"
    finally:
        session.close()


def test_upload_manager_keeps_job_tags_when_provided(client):
    """When job-level `tags` is non-empty, channel default is NOT used."""
    ch_id = _seed_channel(client, name="JobTags", channel_id="UC-JT")
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        ch = session.query(Channel).filter(Channel.id == ch_id).first()
        ch.default_tags = "channel-default"
        session.commit()

        mgr = UploadManager()
        job_id = mgr.create_job(
            routing=[
                {
                    "channel_id": ch_id,
                    "file_path": "/tmp/fake.mp4",
                    "file_name": "fake.mp4",
                }
            ],
            thumbnail_path=None,
            privacy="private",
            description="d",
            tags="job-level-tags",
            scheduled_at=None,
            db=session,
        )
        uploads = session.query(Upload).filter(Upload.job_id == job_id).all()
        assert uploads[0].tags == "job-level-tags"
    finally:
        session.close()


def test_pull_youtube_tags_endpoint_parses_keywords(client):
    """POST /pull-youtube-tags/{id} shlex-splits brandingSettings.keywords."""
    ch_id = _seed_channel(client, name="Puller", channel_id="UC-Pull")

    fake_yt = MagicMock()
    fake_yt.channels.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "brandingSettings": {
                    "channel": {
                        "keywords": '"recap de anime" anime "anime recap"'
                    }
                }
            }
        ]
    }

    with patch(
        "backend.services.oauth_service.oauth_service.load_credentials",
        return_value=MagicMock(),
    ), patch(
        "backend.services.oauth_service.oauth_service.get_youtube_service",
        return_value=fake_yt,
    ):
        r = client.post(f"/api/channels/{ch_id}/pull-youtube-tags")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_tags"] == "recap de anime, anime, anime recap"


def test_pull_youtube_tags_endpoint_handles_empty_keywords(client):
    ch_id = _seed_channel(client, name="EmptyTags", channel_id="UC-Empty")

    fake_yt = MagicMock()
    fake_yt.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"brandingSettings": {"channel": {}}}]
    }

    with patch(
        "backend.services.oauth_service.oauth_service.load_credentials",
        return_value=MagicMock(),
    ), patch(
        "backend.services.oauth_service.oauth_service.get_youtube_service",
        return_value=fake_yt,
    ):
        r = client.post(f"/api/channels/{ch_id}/pull-youtube-tags")
    assert r.status_code == 200, r.text
    assert r.json()["default_tags"] is None


def test_pull_youtube_tags_for_all_aggregates_results(client):
    ch_a = _seed_channel(client, name="A1", channel_id="UC-A1")
    ch_b = _seed_channel(client, name="B1", channel_id="UC-B1")

    fake_yt = MagicMock()
    fake_yt.channels.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "brandingSettings": {
                    "channel": {"keywords": 'one two "three four"'}
                }
            }
        ]
    }

    with patch(
        "backend.services.oauth_service.oauth_service.load_credentials",
        return_value=MagicMock(),
    ), patch(
        "backend.services.oauth_service.oauth_service.get_youtube_service",
        return_value=fake_yt,
    ):
        r = client.post("/api/channels/pull-youtube-tags/all")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2
    assert body["failed"] == 0
    by_id = {res["channel_id"]: res for res in body["results"]}
    assert by_id[ch_a]["ok"] is True
    assert by_id[ch_b]["ok"] is True

    channels = client.get("/api/channels").json()
    for c in channels:
        if c["id"] in (ch_a, ch_b):
            assert c["default_tags"] == "one, two, three four"
