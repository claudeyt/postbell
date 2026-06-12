from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.project import Project
from backend.models.account import Account
from backend.models.channel import Channel
from backend.schemas.account import (
    AccountResponse,
    AuthInstalledStartRequest,
    AuthInstalledStartResponse,
    AuthStartRequest,
    AuthStartResponse,
)
from backend.schemas.channel import ChannelResponse
from backend.services.oauth_service import oauth_service
from backend.services.language_service import language_service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _persist_auth_result(
    db: Session, credentials: Credentials, project_id: int
) -> tuple[Account, int, int]:
    """Shared post-auth bookkeeping for both web and installed flows.

    Resolves the user's email, saves the token file, upserts the Account row,
    and discovers + persists any channels the credentials can manage. Returns
    (account, channels_added, total_channels). Channel discovery failures are
    swallowed (auth itself should still succeed even if channels.list times
    out) — the count returned for discovered channels in that case is 0.
    """
    try:
        email = oauth_service.get_user_email(credentials)
    except Exception:
        email = "unknown@email.com"

    token_path = oauth_service.save_token(email, credentials)

    existing = db.query(Account).filter(Account.email == email).first()
    if existing:
        existing.token_path = token_path
        existing.token_valid = True
        existing.project_id = project_id
        db.commit()
        account = existing
    else:
        account = Account(
            email=email,
            project_id=project_id,
            token_path=token_path,
            token_valid=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

    channels_added = 0
    total_channels = 0
    try:
        discovered = oauth_service.discover_channels(credentials)
        total_channels = len(discovered)
        for ch_data in discovered:
            existing_ch = (
                db.query(Channel)
                .filter(Channel.channel_id == ch_data["channel_id"])
                .first()
            )
            if not existing_ch:
                channel = Channel(
                    account_id=account.id,
                    channel_id=ch_data["channel_id"],
                    channel_name=ch_data["channel_name"],
                    thumbnail_url=ch_data.get("thumbnail_url"),
                    language_code=language_service.detect_language(
                        ch_data["channel_name"]
                    )[0]
                    or "",
                )
                db.add(channel)
                channels_added += 1
        db.commit()
    except Exception:
        pass  # Channel discovery failure shouldn't break auth

    return account, channels_added, total_channels


@router.get("", response_model=list[AccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).all()


@router.post("/auth/start", response_model=AuthStartResponse)
def start_auth(req: AuthStartRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == req.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    auth_url, state = oauth_service.start_auth_flow(
        project.client_secret_path, project.id
    )
    return AuthStartResponse(auth_url=auth_url, state=state)


@router.get("/auth/callback")
def auth_callback(state: str, code: str, db: Session = Depends(get_db)):
    """[LEGACY] Web-flow OAuth callback at the hardcoded :8001 redirect URI.

    Kept for backward compatibility with the pre-Electron dev workflow. New
    Electron clients use POST /auth/start_installed instead, which uses an
    InstalledAppFlow with a random loopback port (no fixed redirect URI to
    pre-register in GCP).
    """
    try:
        credentials, project_id = oauth_service.complete_auth_flow(state, code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    account, _, _ = _persist_auth_result(db, credentials, project_id)

    # Return HTML page that notifies the opener window
    return HTMLResponse(
        content="""
    <!DOCTYPE html>
    <html>
    <head><title>Postbell - Auth Success</title></head>
    <body style="background:#0a0a0a;color:white;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
        <div style="text-align:center">
            <h1>Authentication Successful!</h1>
            <p>You can close this tab and return to Postbell.</p>
            <script>
                if (window.opener) {
                    window.opener.postMessage({ type: 'oauth_complete', email: '"""
        + account.email
        + """' }, '*');
                }
                setTimeout(() => window.close(), 3000);
            </script>
        </div>
    </body>
    </html>
    """
    )


@router.post("/auth/start_installed", response_model=AuthInstalledStartResponse)
def start_installed_auth(
    req: AuthInstalledStartRequest, db: Session = Depends(get_db)
):
    """Start the desktop (installed-app) OAuth flow.

    BLOCKS for up to 5 minutes while the user completes the Google consent
    screen in their default browser. Google redirects to a temporary loopback
    listener spawned by ``InstalledAppFlow.run_local_server``; once the code
    arrives we exchange it for tokens, persist them, and discover channels.

    The client_secret.json registered for the GCP project MUST be of type
    "Desktop application" — Web-type credentials will fail with
    redirect_uri_mismatch because the loopback port is chosen at runtime.

    Returns the discovered account + channel counts. The frontend doesn't
    open a popup window for this flow (the browser opens automatically via
    Python's ``webbrowser.open``).
    """
    project = db.query(Project).filter(Project.id == req.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        credentials = oauth_service.run_installed_flow(project.client_secret_path)
    except Exception as e:
        # Common failures: user closed the browser, timeout (5 min), invalid
        # client_secret.json, redirect_uri_mismatch (Web-type creds), or the
        # local listener could not bind. Surface as 400 so the UI can show
        # something actionable.
        raise HTTPException(
            status_code=400,
            detail=f"OAuth flow failed: {type(e).__name__}: {e}",
        )

    account, channels_added, total_channels = _persist_auth_result(
        db, credentials, project.id
    )

    return AuthInstalledStartResponse(
        email=account.email,
        account_id=account.id,
        project_id=project.id,
        channels_added=channels_added,
        total_channels=total_channels,
    )


@router.get("/{account_id}/status")
def account_status(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    creds = oauth_service.load_credentials(account.token_path)
    valid = creds is not None and not (creds.expired and not creds.refresh_token)

    if valid != account.token_valid:
        account.token_valid = valid
        db.commit()

    return {"account_id": account.id, "email": account.email, "token_valid": valid}


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Delete token file
    token_path = Path(account.token_path)
    if token_path.exists():
        token_path.unlink()

    db.delete(account)
    db.commit()


@router.get("/{account_id}/channels", response_model=list[ChannelResponse])
def list_account_channels(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return db.query(Channel).filter(Channel.account_id == account_id).all()


@router.post("/{account_id}/sync-channels")
def sync_channels(account_id: int, db: Session = Depends(get_db)):
    """Re-discover channels for an account."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    creds = oauth_service.load_credentials(account.token_path)
    if not creds:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    discovered = oauth_service.discover_channels(creds)
    new_channels = 0
    for ch_data in discovered:
        existing_ch = (
            db.query(Channel)
            .filter(Channel.channel_id == ch_data["channel_id"])
            .first()
        )
        if not existing_ch:
            channel = Channel(
                account_id=account.id,
                channel_id=ch_data["channel_id"],
                channel_name=ch_data["channel_name"],
                thumbnail_url=ch_data.get("thumbnail_url"),
                language_code=language_service.detect_language(ch_data["channel_name"])[0] or "",
            )
            db.add(channel)
            new_channels += 1
    db.commit()

    return {"synced": len(discovered), "new_channels": new_channels}
