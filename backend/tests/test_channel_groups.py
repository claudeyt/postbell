"""Tests for the channel groups + reordering feature.

What we pin here:

* POST /api/channel-groups creates a group; GET lists in display_order;
  the auto-assigned display_order is monotonically increasing (0, 1, 2, ...).
* PATCH /api/channel-groups/{id} updates name and display_order independently.
* PATCH /api/channel-groups/reorder rewrites display_order based on array
  index in the submitted ids list.
* DELETE /api/channel-groups/{id} removes the group AND sets group_id=NULL on
  any channels that were in it (explicit, because SQLite does not enforce FK
  ON DELETE SET NULL by default).
* PATCH /api/channels/{id}/group sets/clears channel.group_id; 404s on a
  non-existent group_id.
* PATCH /api/channels/reorder sets channel.display_order to the array index.
* GET /api/channels response shape includes group_id (null default) and
  display_order (0 default) for fresh channels.
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


@pytest.fixture()
def client(tmp_path):
    """TestClient backed by a fresh per-test SQLite DB via get_db override."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'channel_groups_test.db'}",
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
    # Expose the session factory so tests can seed channels directly.
    test_client._SessionLocal = TestSessionLocal  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _seed_channel(client, *, name="Chan A", channel_id="UC-A"):
    """Insert a Project -> Account -> Channel chain. Returns channel.id."""
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


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------


def test_create_and_list_groups_assigns_increasing_display_order(client):
    r1 = client.post("/api/channel-groups", json={"name": "Cooking"})
    assert r1.status_code == 200, r1.text
    g1 = r1.json()
    assert g1["name"] == "Cooking"
    assert g1["display_order"] == 0

    r2 = client.post("/api/channel-groups", json={"name": "Gaming"})
    assert r2.status_code == 200, r2.text
    g2 = r2.json()
    assert g2["display_order"] == 1

    listed = client.get("/api/channel-groups").json()
    assert [g["name"] for g in listed] == ["Cooking", "Gaming"]
    assert [g["display_order"] for g in listed] == [0, 1]


def test_patch_group_updates_name_and_display_order(client):
    gid = client.post("/api/channel-groups", json={"name": "Old"}).json()["id"]

    r = client.patch(f"/api/channel-groups/{gid}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"

    r2 = client.patch(f"/api/channel-groups/{gid}", json={"display_order": 7})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["display_order"] == 7
    # name unchanged from previous patch
    assert body["name"] == "Renamed"


def test_reorder_groups_swaps_their_display_order(client):
    g1 = client.post("/api/channel-groups", json={"name": "First"}).json()
    g2 = client.post("/api/channel-groups", json={"name": "Second"}).json()
    assert g1["display_order"] == 0 and g2["display_order"] == 1

    # Submit ids in reversed order -> g2 becomes 0, g1 becomes 1.
    r = client.patch(
        "/api/channel-groups/reorder", json={"ids": [g2["id"], g1["id"]]}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 2}

    listed = client.get("/api/channel-groups").json()
    assert [g["name"] for g in listed] == ["Second", "First"]
    assert [g["display_order"] for g in listed] == [0, 1]


def test_delete_group_clears_channel_group_id_without_deleting_channels(client):
    """Per spec: deleting a group sets each member channel's group_id to NULL.
    The channels themselves must survive (NOT cascaded to delete)."""
    gid = client.post("/api/channel-groups", json={"name": "Doomed"}).json()["id"]
    ch_id = _seed_channel(client, name="Chan-Doomed", channel_id="UC-Doomed")
    move = client.patch(f"/api/channels/{ch_id}/group", json={"group_id": gid})
    assert move.status_code == 200, move.text
    assert move.json()["group_id"] == gid

    r = client.delete(f"/api/channel-groups/{gid}")
    assert r.status_code == 204, r.text

    # Group gone from list.
    listed = client.get("/api/channel-groups").json()
    assert all(g["id"] != gid for g in listed)

    # Channel survives with group_id == None.
    channels = client.get("/api/channels").json()
    survivors = [c for c in channels if c["id"] == ch_id]
    assert len(survivors) == 1
    assert survivors[0]["group_id"] is None


# ---------------------------------------------------------------------------
# Channel move-to-group + reorder
# ---------------------------------------------------------------------------


def test_move_channel_to_group_set_clear_and_404(client):
    ch_id = _seed_channel(client, name="Mover", channel_id="UC-Mover")
    gid = client.post("/api/channel-groups", json={"name": "G1"}).json()["id"]

    # Set
    r1 = client.patch(f"/api/channels/{ch_id}/group", json={"group_id": gid})
    assert r1.status_code == 200, r1.text
    assert r1.json()["group_id"] == gid

    # Clear
    r2 = client.patch(f"/api/channels/{ch_id}/group", json={"group_id": None})
    assert r2.status_code == 200, r2.text
    assert r2.json()["group_id"] is None

    # Non-existent group_id -> 404
    r3 = client.patch(
        f"/api/channels/{ch_id}/group", json={"group_id": 99999}
    )
    assert r3.status_code == 404, r3.text

    # Non-existent channel -> 404
    r4 = client.patch("/api/channels/88888/group", json={"group_id": None})
    assert r4.status_code == 404, r4.text


def test_reorder_channels_sets_display_order_by_index(client):
    ch_a = _seed_channel(client, name="A", channel_id="UC-A")
    ch_b = _seed_channel(client, name="B", channel_id="UC-B")
    ch_c = _seed_channel(client, name="C", channel_id="UC-C")

    # Submit C, A, B -> display_orders should be 0, 1, 2 respectively.
    r = client.patch(
        "/api/channels/reorder", json={"ids": [ch_c, ch_a, ch_b]}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 3}

    channels = {c["id"]: c for c in client.get("/api/channels").json()}
    assert channels[ch_c]["display_order"] == 0
    assert channels[ch_a]["display_order"] == 1
    assert channels[ch_b]["display_order"] == 2


def test_channel_response_includes_group_id_and_display_order_defaults(client):
    ch_id = _seed_channel(client, name="Fresh", channel_id="UC-Fresh")
    channels = client.get("/api/channels").json()
    found = [c for c in channels if c["id"] == ch_id]
    assert len(found) == 1
    body = found[0]
    assert "group_id" in body and body["group_id"] is None
    assert "display_order" in body and body["display_order"] == 0
