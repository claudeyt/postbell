from typing import Optional

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    gemini_api_key: str
    upload_chunk_size_mb: int
    youtube_daily_quota: int
    default_privacy: str
    default_description: str
    default_tags: list[str]


class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    upload_chunk_size_mb: Optional[int] = None
    youtube_daily_quota: Optional[int] = None
    default_privacy: Optional[str] = None
    default_description: Optional[str] = None
    default_tags: Optional[list[str]] = None
