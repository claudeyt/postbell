import json
import os
from pathlib import Path

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from backend.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]
# Used by the legacy web flow (start_auth_flow / complete_auth_flow). The
# installed-app flow does not use this — google_auth_oauthlib picks a free
# localhost port and registers its own redirect_uri at runtime.
REDIRECT_URI = "http://localhost:8001/api/accounts/auth/callback"


class OAuthService:
    def __init__(self):
        self._pending_flows: dict[str, dict] = {}  # state -> {flow, project_id}

    def start_auth_flow(self, client_secret_path: str, project_id: int) -> tuple[str, str]:
        """[DEPRECATED] Start OAuth web flow. Returns (auth_url, state).

        Kept for backward compatibility with the pre-Electron dev workflow that
        used a fixed redirect URI at :8001. New code (Electron mode) should
        call ``run_installed_flow`` instead. Existing token files stay
        compatible because they store refresh_token + client_secret directly,
        so ``load_credentials`` can refresh them regardless of which flow
        originally produced them.
        """
        flow = Flow.from_client_secrets_file(
            client_secret_path,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        self._pending_flows[state] = {"flow": flow, "project_id": project_id}
        return auth_url, state

    def complete_auth_flow(self, state: str, code: str) -> tuple[Credentials, int]:
        """[DEPRECATED] Complete OAuth web flow. Returns (credentials, project_id).

        See ``start_auth_flow`` for context. Kept alongside the new
        installed-app flow so the legacy /api/accounts/auth/callback endpoint
        still works for any in-flight authorizations.
        """
        if state not in self._pending_flows:
            raise ValueError("Invalid or expired OAuth state")
        flow_data = self._pending_flows.pop(state)
        flow = flow_data["flow"]
        project_id = flow_data["project_id"]
        flow.fetch_token(code=code)
        return flow.credentials, project_id

    def run_installed_flow(
        self, client_secret_path: str, port: int = 0
    ) -> Credentials:
        """Run the desktop OAuth flow.

        Uses ``InstalledAppFlow`` which:
          - binds a temporary HTTP listener on a free loopback port (port=0)
          - opens the user's default browser to Google's consent page
          - captures the redirect locally and exchanges the code for tokens

        This is the only flow that works inside Electron, because the random
        backend port + bundled exe means we can't pre-register a fixed
        redirect URI in Google Cloud Console.

        BLOCKS until the user completes auth or ``timeout_seconds`` elapses.
        Requires the ``client_secret.json`` to be of type "Desktop application"
        (not "Web application") — Web-type credentials will be rejected by
        Google with a redirect_uri_mismatch.

        Returns Google ``Credentials`` ready to be persisted via
        ``save_token``.
        """
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret_path,
            scopes=SCOPES,
        )
        creds = flow.run_local_server(
            port=port,
            open_browser=True,
            timeout_seconds=300,  # 5 min
        )
        return creds

    def save_token(self, email: str, credentials: Credentials) -> str:
        """Save credentials to data/tokens/{email}.json. Returns the path."""
        settings.tokens_dir.mkdir(parents=True, exist_ok=True)
        token_path = settings.tokens_dir / f"{email}.json"
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or []),
        }
        token_path.write_text(json.dumps(token_data, indent=2))
        return str(token_path)

    def load_credentials(self, token_path: str) -> Credentials | None:
        """Load credentials from a token file. Auto-refresh if expired."""
        path = Path(token_path)
        if not path.exists():
            return None
        token_data = json.loads(path.read_text())
        creds = Credentials(
            token=token_data["token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.save_token(Path(token_path).stem, creds)
        return creds

    def get_youtube_service(self, credentials: Credentials):
        """Build an authenticated YouTube API service object."""
        return build("youtube", "v3", credentials=credentials)

    def get_analytics_service(self, credentials: Credentials):
        """Build an authenticated YouTube Analytics API service object."""
        return build("youtubeAnalytics", "v2", credentials=credentials)

    def get_user_email(self, credentials: Credentials) -> str:
        """Get the authenticated user's email."""
        from googleapiclient.discovery import build as build_service

        service = build_service("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()
        return user_info.get("email", "unknown@email.com")

    def discover_channels(self, credentials: Credentials) -> list[dict]:
        """Discover all YouTube channels the account can manage."""
        youtube = self.get_youtube_service(credentials)
        channels = []

        request = youtube.channels().list(part="snippet,brandingSettings", mine=True)
        response = request.execute()
        for item in response.get("items", []):
            channels.append(
                {
                    "channel_id": item["id"],
                    "channel_name": item["snippet"]["title"],
                    "thumbnail_url": item["snippet"]["thumbnails"]
                    .get("default", {})
                    .get("url"),
                }
            )

        return channels


oauth_service = OAuthService()
