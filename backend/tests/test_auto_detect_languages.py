"""Tests for the POST /api/channels/auto-detect-languages endpoint.

What we pin here:

* Channels with language_code IS NULL get a detected code written to the DB
  when the language_service cascade returns a code in LANGUAGE_SUFFIXES.
* Channels that already have a language_code are NOT touched and are counted
  in skipped_already_set (a count of pre-existing language_code-set channels
  in the whole table, regardless of whether the cascade would have changed
  them).
* Channels that don't resolve via the cascade are counted in skipped_unknown.
* The response includes a per-channel results array with channel_id,
  channel_name, detected_language, method, set.
* The endpoint is reachable at /api/channels/auto-detect-languages (i.e. it
  is NOT shadowed by /{channel_id} — verifies route ordering).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models.account import Account
from backend.models.channel import Channel
from backend.models.channel_group import ChannelGroup  # noqa: F401 -- table creation
from backend.models.project import Project
from backend.models.quota import QuotaUsage  # noqa: F401 -- table creation
from backend.models.upload import Upload  # noqa: F401 -- table creation
from backend.services import language_service as language_service_module


@pytest.fixture()
def client(tmp_path):
    """TestClient backed by a fresh per-test SQLite DB via get_db override."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auto_detect_test.db'}",
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


def _seed_account(client) -> int:
    """Insert a Project -> Account chain. Returns account.id."""
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        project = Project(
            name="P-AutoDetect",
            client_secret_path="/fake/auto-detect.json",
            daily_quota_limit=10000,
        )
        session.add(project)
        session.commit()

        account = Account(
            email="auto-detect@example.com",
            project_id=project.id,
            token_path="/fake/auto-detect-token.json",
        )
        session.add(account)
        session.commit()
        return account.id
    finally:
        session.close()


def _seed_channel(
    client,
    *,
    account_id: int,
    name: str,
    channel_id: str,
    language_code: str | None,
) -> int:
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        ch = Channel(
            account_id=account_id,
            channel_id=channel_id,
            channel_name=name,
            language_code=language_code,
        )
        session.add(ch)
        session.commit()
        return ch.id
    finally:
        session.close()


# Deterministic stand-in for Gemini so tests don't depend on network or API key.
_GEMINI_OVERRIDES: dict[str, str | None] = {
    "Raijin - Anime Recaps": "en",
    "Raijin - Anime Francais": "fr",
    "Riassunti Anime": "it",
}


@pytest.fixture(autouse=True)
def _stub_gemini(monkeypatch):
    """Replace _detect_by_gemini with a deterministic name -> code lookup."""

    def _fake_gemini(self, text: str):
        return _GEMINI_OVERRIDES.get(text)

    monkeypatch.setattr(
        language_service_module.LanguageService,
        "_detect_by_gemini",
        _fake_gemini,
    )
    yield


def test_auto_detect_updates_unset_skips_preset_and_returns_summary(client):
    account_id = _seed_account(client)

    # 3 unset channels that will all get a code:
    #   - "Raijin - Anime Recaps" -> Gemini stub returns "en"
    #   - "Raijin - Anime Francais" -> Gemini stub returns "fr"
    #   - "Riassunti Anime" -> Gemini stub returns "it"
    # 2 pre-set channels (must be UNTOUCHED):
    #   - "Anime Resumenes" with language_code="es"
    #   - "Hakari - Anime Hindi" with language_code="hi"
    ch_en_id = _seed_channel(
        client,
        account_id=account_id,
        name="Raijin - Anime Recaps",
        channel_id="UC-EN",
        language_code="",
    )
    ch_fr_id = _seed_channel(
        client,
        account_id=account_id,
        name="Raijin - Anime Francais",
        channel_id="UC-FR",
        language_code="",
    )
    ch_it_id = _seed_channel(
        client,
        account_id=account_id,
        name="Riassunti Anime",
        channel_id="UC-IT",
        language_code="",
    )
    ch_es_id = _seed_channel(
        client,
        account_id=account_id,
        name="Anime Resumenes",
        channel_id="UC-ES",
        language_code="es",
    )
    ch_hi_id = _seed_channel(
        client,
        account_id=account_id,
        name="Hakari - Anime Hindi",
        channel_id="UC-HI",
        language_code="hi",
    )

    r = client.post("/api/channels/auto-detect-languages")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["updated"] == 3
    assert body["skipped_unknown"] == 0
    assert body["skipped_already_set"] == 2

    # Per-channel results array present with one entry per processed candidate.
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 3
    by_id = {row["channel_id"]: row for row in body["results"]}
    assert by_id[ch_en_id]["detected_language"] == "en"
    assert by_id[ch_en_id]["set"] is True
    assert by_id[ch_fr_id]["detected_language"] == "fr"
    assert by_id[ch_fr_id]["set"] is True
    assert by_id[ch_it_id]["detected_language"] == "it"
    assert by_id[ch_it_id]["set"] is True

    # Pre-set channels stay UNCHANGED in the DB.
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        es = session.query(Channel).filter(Channel.id == ch_es_id).first()
        hi = session.query(Channel).filter(Channel.id == ch_hi_id).first()
        assert es is not None and es.language_code == "es"
        assert hi is not None and hi.language_code == "hi"

        # The 3 unset channels now have the detected codes persisted.
        en = session.query(Channel).filter(Channel.id == ch_en_id).first()
        fr = session.query(Channel).filter(Channel.id == ch_fr_id).first()
        it = session.query(Channel).filter(Channel.id == ch_it_id).first()
        assert en is not None and en.language_code == "en"
        assert fr is not None and fr.language_code == "fr"
        assert it is not None and it.language_code == "it"
    finally:
        session.close()


def test_auto_detect_counts_unknown_when_cascade_returns_nothing(client):
    """A channel whose name doesn't resolve via any cascade layer is reported
    in skipped_unknown and is NOT updated."""
    account_id = _seed_account(client)
    ch_id = _seed_channel(
        client,
        account_id=account_id,
        name="ZZZ-mystery-name",  # not in gemini stub -> stub returns None
        channel_id="UC-ZZZ",
        language_code="",
    )

    r = client.post("/api/channels/auto-detect-languages")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["updated"] == 0
    assert body["skipped_unknown"] == 1
    assert body["skipped_already_set"] == 0
    assert len(body["results"]) == 1
    row = body["results"][0]
    assert row["channel_id"] == ch_id
    assert row["detected_language"] is None
    assert row["set"] is False

    # DB unchanged.
    SessionLocal = client._SessionLocal  # type: ignore[attr-defined]
    session = SessionLocal()
    try:
        ch = session.query(Channel).filter(Channel.id == ch_id).first()
        # Unset channels start with "" and stay "" if no detection succeeded.
        assert ch is not None and (ch.language_code is None or ch.language_code == "")
    finally:
        session.close()


def test_auto_detect_returns_empty_summary_when_no_channels(client):
    """No channels at all -> all counts are zero, empty results array."""
    r = client.post("/api/channels/auto-detect-languages")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "updated": 0,
        "skipped_unknown": 0,
        "skipped_already_set": 0,
        "results": [],
    }


def test_auto_detect_route_not_shadowed_by_channel_id_path(client):
    """Regression: /auto-detect-languages must be declared before /{channel_id}
    so FastAPI matches it as a literal path. If route ordering regressed, this
    POST would 422 (cannot coerce 'auto-detect-languages' to int) or hit the
    wrong handler."""
    r = client.post("/api/channels/auto-detect-languages")
    assert r.status_code == 200, r.text
    # Sanity: response shape is from auto_detect_languages, not update_channel.
    body = r.json()
    assert "updated" in body
    assert "skipped_unknown" in body
    assert "skipped_already_set" in body
    assert "results" in body
