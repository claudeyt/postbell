from unittest.mock import MagicMock, patch

import pytest

from backend.services.youtube_service import YouTubeService


def _make_mock_youtube_service():
    """Return (yt_service_mock, captured) where captured['body'] holds the
    body kwarg passed to .videos().insert(...)."""
    captured = {}

    request = MagicMock()
    # Resumable loop: next_chunk returns finished response immediately.
    request.next_chunk.return_value = (None, {"id": "TESTVIDEOID"})

    def insert(*args, **kwargs):
        captured["body"] = kwargs.get("body")
        captured["part"] = kwargs.get("part")
        return request

    videos = MagicMock()
    videos.insert.side_effect = insert

    yt_service = MagicMock()
    yt_service.videos.return_value = videos

    return yt_service, captured


@patch("backend.services.youtube_service.MediaFileUpload")
def test_language_set_adds_default_language_keys(mock_media):
    mock_media.return_value = MagicMock()
    yt_service, captured = _make_mock_youtube_service()

    result = YouTubeService().upload_video(
        youtube_service=yt_service,
        file_path="/fake/path/video.mp4",
        title="My Title",
        description="desc",
        tags="a,b",
        language="es",
    )

    assert result["video_id"] == "TESTVIDEOID"
    snippet = captured["body"]["snippet"]
    assert snippet["defaultLanguage"] == "es"
    assert snippet["defaultAudioLanguage"] == "es"


@patch("backend.services.youtube_service.MediaFileUpload")
def test_language_none_omits_default_language_keys(mock_media):
    mock_media.return_value = MagicMock()
    yt_service, captured = _make_mock_youtube_service()

    YouTubeService().upload_video(
        youtube_service=yt_service,
        file_path="/fake/path/video.mp4",
        title="My Title",
        language=None,
    )

    snippet = captured["body"]["snippet"]
    assert "defaultLanguage" not in snippet
    assert "defaultAudioLanguage" not in snippet


@patch("backend.services.youtube_service.MediaFileUpload")
def test_language_omitted_omits_default_language_keys(mock_media):
    mock_media.return_value = MagicMock()
    yt_service, captured = _make_mock_youtube_service()

    YouTubeService().upload_video(
        youtube_service=yt_service,
        file_path="/fake/path/video.mp4",
        title="My Title",
    )

    snippet = captured["body"]["snippet"]
    assert "defaultLanguage" not in snippet
    assert "defaultAudioLanguage" not in snippet


@patch("backend.services.youtube_service.MediaFileUpload")
def test_empty_string_language_omits_default_language_keys(mock_media):
    """Empty string is falsy, so keys must be omitted."""
    mock_media.return_value = MagicMock()
    yt_service, captured = _make_mock_youtube_service()

    YouTubeService().upload_video(
        youtube_service=yt_service,
        file_path="/fake/path/video.mp4",
        title="My Title",
        language="",
    )

    snippet = captured["body"]["snippet"]
    assert "defaultLanguage" not in snippet
    assert "defaultAudioLanguage" not in snippet


def _resolve_language(detected_language, channel_language_code):
    """Mirror of the resolution expression in upload_manager.process_job:

        upload_language = (
            upload.detected_language
            if upload.detected_language
            else (channel.language_code if channel.language_code else None)
        )
    """
    return (
        detected_language
        if detected_language
        else (channel_language_code if channel_language_code else None)
    )


class TestLanguageResolutionPrecedence:
    """Verifies the precedence logic in upload_manager.process_job:
    detected_language wins over channel.language_code, which wins over None.
    Replicated here because wiring the full async DB-backed process_job loop
    is too heavy for a focused unit test."""

    def test_detected_wins_over_channel(self):
        assert _resolve_language("es", "pt") == "es"

    def test_channel_used_when_no_detected(self):
        assert _resolve_language(None, "pt") == "pt"
        assert _resolve_language("", "pt") == "pt"

    def test_none_when_neither(self):
        assert _resolve_language(None, None) is None
        assert _resolve_language("", "") is None
