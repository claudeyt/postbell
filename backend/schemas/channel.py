import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


_HHMM_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


class ChannelUpdate(BaseModel):
    alias: str | None = None
    language_code: str | None = None
    default_description: str | None = None
    default_comment: str | None = None
    default_tags: str | None = None
    is_active: bool | None = None
    custom_schedule_time: str | None = None

    @field_validator("custom_schedule_time", mode="before")
    @classmethod
    def _validate_custom_schedule_time(cls, v: Any) -> Any:
        # Accept null or empty string as "clear", valid HH:MM as set,
        # anything else -> 422.
        if v is None:
            return None
        if isinstance(v, str):
            if v == "":
                return None
            if _HHMM_RE.match(v):
                return v
        raise ValueError("custom_schedule_time must be HH:MM (00:00-23:59) or null")


class ChannelResponse(BaseModel):
    id: int
    account_id: int
    channel_id: str
    channel_name: str
    alias: str | None
    language_code: str
    default_description: str
    default_comment: str
    default_tags: str | None = None
    thumbnail_url: str | None
    is_active: bool
    group_id: int | None = None
    display_order: int = 0
    custom_schedule_time: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
