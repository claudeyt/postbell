from datetime import datetime
from pydantic import BaseModel


class AccountResponse(BaseModel):
    id: int
    email: str
    project_id: int
    token_valid: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthStartRequest(BaseModel):
    project_id: int


class AuthStartResponse(BaseModel):
    auth_url: str
    state: str


class AuthInstalledStartRequest(BaseModel):
    """Body for POST /api/accounts/auth/start_installed.

    The installed-app flow does not need a state token (the temporary local
    HTTP listener in InstalledAppFlow handles correlation), so this is just
    the GCP project whose client_secret.json should drive the auth.
    """

    project_id: int


class AuthInstalledStartResponse(BaseModel):
    """Result of a completed installed-app OAuth flow.

    Returned synchronously once the user finishes the browser handshake —
    the endpoint blocks for up to 5 min waiting for them.
    """

    email: str
    account_id: int
    project_id: int
    channels_added: int
    total_channels: int
