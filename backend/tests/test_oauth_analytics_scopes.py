from unittest.mock import MagicMock, patch

from backend.services.oauth_service import SCOPES, OAuthService

ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
ANALYTICS_MONETARY_SCOPE = (
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"
)
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
FORCE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def test_analytics_scopes_present():
    """Both YouTube Analytics scopes must be in SCOPES (exact match)."""
    assert ANALYTICS_SCOPE in SCOPES
    assert ANALYTICS_MONETARY_SCOPE in SCOPES


def test_upload_scopes_not_removed():
    """Regression: pre-existing upload scopes must still be present."""
    assert UPLOAD_SCOPE in SCOPES
    assert FORCE_SSL_SCOPE in SCOPES


@patch("backend.services.oauth_service.build")
def test_get_analytics_service_builds_youtube_analytics_v2(mock_build):
    """get_analytics_service must call build("youtubeAnalytics", "v2",
    credentials=<creds>)."""
    dummy_creds = MagicMock(name="dummy_credentials")
    sentinel_service = MagicMock(name="analytics_service")
    mock_build.return_value = sentinel_service

    result = OAuthService().get_analytics_service(dummy_creds)

    assert result is sentinel_service
    mock_build.assert_called_once_with(
        "youtubeAnalytics", "v2", credentials=dummy_creds
    )


def test_oauthlib_relax_token_scope_env_set():
    """Importing the module sets OAUTHLIB_RELAX_TOKEN_SCOPE=1."""
    import os

    assert os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE") == "1"
