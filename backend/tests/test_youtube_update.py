from unittest.mock import MagicMock

from backend.services.youtube_service import YouTubeService


def _make_mock_youtube_service():
    """Return (yt_service_mock, captured) where captured holds the kwargs
    passed to .videos().update(...)."""
    captured = {}

    request = MagicMock()
    request.execute.return_value = {"id": "TESTVIDEOID", "ok": True}

    def update(*args, **kwargs):
        captured["body"] = kwargs.get("body")
        captured["part"] = kwargs.get("part")
        return request

    videos = MagicMock()
    videos.update.side_effect = update

    yt_service = MagicMock()
    yt_service.videos.return_value = videos

    return yt_service, captured


def test_update_video_builds_correct_request():
    yt_service, captured = _make_mock_youtube_service()

    result = YouTubeService().update_video(
        youtube_service=yt_service,
        video_id="VID123",
        title="New Title",
        description="New description",
        tags="alpha, beta , gamma",
        privacy="unlisted",
    )

    # Returns the API response untouched.
    assert result == {"id": "TESTVIDEOID", "ok": True}

    # part must include both snippet and status.
    assert captured["part"] == "snippet,status"

    body = captured["body"]
    assert body["id"] == "VID123"

    snippet = body["snippet"]
    assert snippet["title"] == "New Title"
    assert snippet["description"] == "New description"
    # Comma split with whitespace stripped, empties removed.
    assert snippet["tags"] == ["alpha", "beta", "gamma"]
    assert snippet["categoryId"] == "22"

    assert body["status"]["privacyStatus"] == "unlisted"


def test_update_video_truncates_title_to_100_chars():
    yt_service, captured = _make_mock_youtube_service()

    long_title = "x" * 150
    YouTubeService().update_video(
        youtube_service=yt_service,
        video_id="VID123",
        title=long_title,
        description="d",
        tags="",
        privacy="private",
    )

    snippet = captured["body"]["snippet"]
    assert len(snippet["title"]) == 100
    assert snippet["title"] == "x" * 100


def test_update_video_empty_tags_yields_empty_list():
    yt_service, captured = _make_mock_youtube_service()

    YouTubeService().update_video(
        youtube_service=yt_service,
        video_id="VID123",
        title="t",
        description="d",
        tags="",
        privacy="public",
    )

    assert captured["body"]["snippet"]["tags"] == []
    assert captured["body"]["status"]["privacyStatus"] == "public"


def test_update_video_executes_the_request():
    """Ensure .execute() is actually called (the request is sent)."""
    yt_service, _ = _make_mock_youtube_service()
    YouTubeService().update_video(
        youtube_service=yt_service,
        video_id="VID123",
        title="t",
        description="d",
        tags="a",
        privacy="private",
    )
    # The request object returned by update() must have had execute() called.
    request = yt_service.videos().update()
    assert request.execute.called
