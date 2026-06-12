from unittest.mock import MagicMock

from backend.services.youtube_service import YouTubeService


def _make_mock_youtube_service():
    """Return (yt_service_mock, captured) where captured holds the kwargs
    passed to .commentThreads().insert(...)."""
    captured = {}

    request = MagicMock()
    request.execute.return_value = {"id": "COMMENTTHREADID", "ok": True}

    def insert(*args, **kwargs):
        captured["body"] = kwargs.get("body")
        captured["part"] = kwargs.get("part")
        return request

    comment_threads = MagicMock()
    comment_threads.insert.side_effect = insert

    yt_service = MagicMock()
    yt_service.commentThreads.return_value = comment_threads

    return yt_service, captured, request


def test_post_comment_builds_correct_request():
    yt_service, captured, request = _make_mock_youtube_service()

    result = YouTubeService().post_comment(
        youtube_service=yt_service,
        video_id="VID123",
        text="Subscribe for more!",
    )

    # Returns the API response untouched on success.
    assert result == {"id": "COMMENTTHREADID", "ok": True}

    # part must be exactly "snippet".
    assert captured["part"] == "snippet"

    # body must match the exact YouTube commentThreads.insert shape.
    assert captured["body"] == {
        "snippet": {
            "videoId": "VID123",
            "topLevelComment": {
                "snippet": {"textOriginal": "Subscribe for more!"},
            },
        },
    }

    # The request must actually be sent.
    assert request.execute.called


def test_post_comment_executes_the_request():
    """Ensure .execute() is actually called (the request is sent)."""
    yt_service, _, request = _make_mock_youtube_service()
    YouTubeService().post_comment(
        youtube_service=yt_service,
        video_id="VID999",
        text="Hello world",
    )
    assert request.execute.called


def test_post_comment_returns_none_and_does_not_raise_on_failure():
    """Non-fatal behavior: if .execute() throws, return None without raising."""
    request = MagicMock()
    request.execute.side_effect = RuntimeError("API blew up")

    comment_threads = MagicMock()
    comment_threads.insert.return_value = request

    yt_service = MagicMock()
    yt_service.commentThreads.return_value = comment_threads

    # Must not raise.
    result = YouTubeService().post_comment(
        youtube_service=yt_service,
        video_id="VID123",
        text="will fail",
    )
    assert result is None
