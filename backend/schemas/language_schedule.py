from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

HHMM = r'^([01]\d|2[0-3]):[0-5]\d$'


class LanguageScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    language_code: str
    time_brt: str
    updated_at: datetime


class LanguageScheduleUpsert(BaseModel):
    time_brt: str = Field(pattern=HHMM)


class ResolvedSchedule(BaseModel):
    channel_id: int
    channel_name: str
    language_code: str | None
    resolved_time: str | None
    source: str  # 'channel' | 'language' | 'none'
    scheduled_at_brt: datetime | None
    scheduled_at_utc: datetime | None
    already_passed: bool
    error: str | None = None


class ResolveScheduleRequest(BaseModel):
    channel_ids: list[int]
    target_date: date | None = None  # YYYY-MM-DD; null = today in BRT
