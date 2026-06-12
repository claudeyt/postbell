import json
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy.orm import Session
from fastapi import Depends

from backend.config import settings as app_settings
from backend.database import get_db
from backend.models.upload import Upload
from backend.schemas.settings import SettingsResponse, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _settings_file() -> Path:
    """Resolve settings.json lazily so it honours POSTBELL_DATA_DIR overrides.

    Resolving once at import time would freeze the path to whatever data_dir
    was when this module loaded — fine in prod, but tests that mutate
    settings.data_dir would still hit the original location.
    """
    return app_settings.settings_file

_DEFAULTS: dict = {
    "gemini_api_key": "",
    "upload_chunk_size_mb": 10,
    "youtube_daily_quota": 10000,
    "default_privacy": "private",
    "default_description": "",
    "default_tags": [],
}


def _load() -> dict:
    """Load settings from settings.json (under data_dir), falling back to defaults."""
    settings_file = _settings_file()
    if settings_file.exists():
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            merged = {**_DEFAULTS, **data}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return {
        **_DEFAULTS,
        "gemini_api_key": app_settings.gemini_api_key,
        "upload_chunk_size_mb": app_settings.upload_chunk_size_mb,
        "youtube_daily_quota": app_settings.youtube_daily_quota,
    }


def _save(data: dict) -> None:
    settings_file = _settings_file()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return f"sk-****{key[-4:]}"


@router.get("/gemini-key")
def get_gemini_key():
    """Return the real (unmasked) Gemini API key."""
    data = _load()
    return {"gemini_api_key": data.get("gemini_api_key", "")}


@router.post("/test-gemini")
def test_gemini():
    """Test the Gemini API key by making a simple request."""
    data = _load()
    key = data.get("gemini_api_key", "")
    if not key:
        return {"success": False, "error": "No Gemini API key configured"}

    try:
        from google import genai
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Return only the word: OK",
        )
        return {"success": True, "response": response.text.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    data = _load()
    return SettingsResponse(
        gemini_api_key=_mask_key(data.get("gemini_api_key", "")),
        upload_chunk_size_mb=data.get("upload_chunk_size_mb", _DEFAULTS["upload_chunk_size_mb"]),
        youtube_daily_quota=data.get("youtube_daily_quota", _DEFAULTS["youtube_daily_quota"]),
        default_privacy=data.get("default_privacy", _DEFAULTS["default_privacy"]),
        default_description=data.get("default_description", _DEFAULTS["default_description"]),
        default_tags=data.get("default_tags", _DEFAULTS["default_tags"]),
    )


@router.put("", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate) -> SettingsResponse:
    data = _load()

    if body.gemini_api_key is not None:
        data["gemini_api_key"] = body.gemini_api_key
    if body.upload_chunk_size_mb is not None:
        data["upload_chunk_size_mb"] = body.upload_chunk_size_mb
    if body.youtube_daily_quota is not None:
        data["youtube_daily_quota"] = body.youtube_daily_quota
    if body.default_privacy is not None:
        data["default_privacy"] = body.default_privacy
    if body.default_description is not None:
        data["default_description"] = body.default_description
    if body.default_tags is not None:
        data["default_tags"] = body.default_tags

    _save(data)

    return SettingsResponse(
        gemini_api_key=_mask_key(data.get("gemini_api_key", "")),
        upload_chunk_size_mb=data["upload_chunk_size_mb"],
        youtube_daily_quota=data["youtube_daily_quota"],
        default_privacy=data["default_privacy"],
        default_description=data["default_description"],
        default_tags=data["default_tags"],
    )


@router.post("/clear-temp")
def clear_temp_folder(db: Session = Depends(get_db)) -> dict:
    """Delete every file in data/temp/. Refuses to run while uploads are
    actively in progress (status='uploading' or 'pending') so we don't yank
    a file out from under an in-flight upload.

    Returns {deleted: int, freed_bytes: int, freed_mb: float}.
    """
    # Safety check: don't clear if there are uploads in flight
    in_flight = db.query(Upload).filter(
        Upload.status.in_(["pending", "uploading"])
    ).count()
    if in_flight > 0:
        from fastapi import HTTPException
        raise HTTPException(
            409,
            f"{in_flight} upload(s) em andamento. Aguarde ou cancele antes de limpar a pasta temp."
        )

    temp_dir = app_settings.temp_dir
    if not temp_dir.exists():
        return {"deleted": 0, "freed_bytes": 0, "freed_mb": 0.0}

    deleted = 0
    freed = 0
    for entry in temp_dir.iterdir():
        try:
            if entry.is_file():
                freed += entry.stat().st_size
                entry.unlink()
                deleted += 1
        except OSError:
            # Skip files that can't be removed (locked, etc.)
            pass

    return {
        "deleted": deleted,
        "freed_bytes": freed,
        "freed_mb": round(freed / (1024 * 1024), 2),
    }
