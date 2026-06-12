"""Tests for chunked upload endpoints (/upload-chunk + /finalize-chunked).

These cover:
* Happy path: 3 chunks -> finalize -> assembled file matches the concatenation
  of the chunk bytes exactly.
* Path-traversal rejection: a malformed X-Upload-Id is rejected with 400 BEFORE
  any filesystem access.
* Missing-chunk detection: if /finalize-chunked is called with a chunk index
  that was never uploaded, it must refuse instead of producing a truncated
  destination file.

The chunked endpoints don't touch the DB, so we don't need the full DB
override fixture from test_uploads_start.py — just app_settings.data_dir
pointed at tmp_path so the temp_dir/ + .chunks/ scratch lives inside the
test directory.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import settings as app_settings
from backend.main import app


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect app_settings.data_dir at tmp_path for the duration of the test.

    All derived paths (temp_dir, .chunks scratch) are resolved at endpoint
    call-time so this monkeypatch is sufficient — no need to restart the app.
    """
    monkeypatch.setattr(app_settings, "data_dir", tmp_path)
    (tmp_path / "temp").mkdir(parents=True, exist_ok=True)
    yield tmp_path


@pytest.fixture()
def client(isolated_data_dir):
    return TestClient(app)


_VALID_UUID = "11111111-2222-3333-4444-555555555555"


def _send_chunk(client: TestClient, *, upload_id: str, index: int, total: int,
                filename: str, body: bytes):
    """POST one chunk via the test client. Returns the response object."""
    return client.post(
        "/api/uploads/upload-chunk",
        content=body,
        headers={
            "X-Upload-Id": upload_id,
            "X-Chunk-Index": str(index),
            "X-Total-Chunks": str(total),
            "X-Filename": filename,
        },
    )


def test_chunk_upload_basic(client, isolated_data_dir):
    """Upload three chunks, finalize, assert the assembled file matches the
    concatenation of the chunk bytes byte-for-byte."""
    payloads = [b"AAAA" * 4, b"BBBBBB" * 3, b"CC"]
    filename = "test_video.mp4"

    for i, body in enumerate(payloads):
        resp = _send_chunk(
            client,
            upload_id=_VALID_UUID,
            index=i,
            total=len(payloads),
            filename=filename,
            body=body,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["chunk_index"] == i
        assert data["received"] is True
        assert data["size"] == len(body)

    final = client.post(
        "/api/uploads/finalize-chunked",
        json={
            "upload_id": _VALID_UUID,
            "filename": filename,
            "total_chunks": len(payloads),
        },
    )
    assert final.status_code == 200, final.text
    result = final.json()
    assert result["name"] == filename
    dest = Path(result["path"])
    assert dest.is_file()
    assert dest.read_bytes() == b"".join(payloads)

    # The scratch directory must be gone after finalize.
    scratch = isolated_data_dir / "temp" / ".chunks" / _VALID_UUID
    assert not scratch.exists(), f"scratch dir {scratch} still present after finalize"


def test_chunk_upload_rejects_bad_uuid(client):
    """An X-Upload-Id that doesn't match the UUID shape must be refused with
    400 — this is the path-traversal guard."""
    resp = _send_chunk(
        client,
        upload_id="../../etc/passwd",
        index=0,
        total=1,
        filename="evil.mp4",
        body=b"payload",
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail", "")
    assert "upload_id" in detail.lower(), detail


def test_chunk_upload_finalize_missing_chunks(client):
    """Upload chunks 0 and 2 (skip 1) then finalize — must refuse with 400
    instead of producing a truncated destination file."""
    filename = "gappy.mp4"
    # Chunk 0
    resp0 = _send_chunk(
        client,
        upload_id=_VALID_UUID,
        index=0,
        total=3,
        filename=filename,
        body=b"first",
    )
    assert resp0.status_code == 200, resp0.text
    # Chunk 2 (skip chunk 1)
    resp2 = _send_chunk(
        client,
        upload_id=_VALID_UUID,
        index=2,
        total=3,
        filename=filename,
        body=b"third",
    )
    assert resp2.status_code == 200, resp2.text

    final = client.post(
        "/api/uploads/finalize-chunked",
        json={
            "upload_id": _VALID_UUID,
            "filename": filename,
            "total_chunks": 3,
        },
    )
    assert final.status_code == 400, final.text
    detail = final.json().get("detail", "")
    assert "missing" in detail.lower(), detail
    # The destination file must NOT have been created.
    assert not (Path(app_settings.temp_dir) / filename).exists()
