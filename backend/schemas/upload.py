from datetime import datetime
from pydantic import BaseModel


class FileInfo(BaseModel):
    name: str
    size: int
    path: str


class PrepareRequest(BaseModel):
    files: list[FileInfo]
    selected_channel_ids: list[int]


class RoutingEntry(BaseModel):
    file_name: str
    file_path: str
    detected_language: str | None
    detection_method: str | None
    channel_id: int | None
    channel_name: str | None
    thumbnail_path: str | None = None
    title: str | None = None
    # Per-entry UTC ISO 8601 timestamp. Populated by the frontend in
    # auto-agendar (per-language) mode so each entry carries its own scheduled
    # publish time. When absent, the /start handler falls back to the legacy
    # job-level scheduled_at + stagger.
    scheduled_at: str | None = None


class PrepareResponse(BaseModel):
    routing: list[RoutingEntry]
    unroutable: list[RoutingEntry]


class StartUploadRequest(BaseModel):
    job_id: str
    routing: list[RoutingEntry]
    thumbnail_path: str | None = None
    privacy: str = "private"
    description: str = ""
    tags: str = ""
    scheduled_at: str | None = None
    stagger_minutes: int | None = None


class YoutubeEditRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: str | None = None
    privacy: str | None = None


class UploadResponse(BaseModel):
    id: int
    job_id: str
    channel_id: int
    file_name: str
    title: str
    status: str
    youtube_video_id: str | None
    youtube_url: str | None
    progress_percent: float
    error_message: str | None
    verification_error: str | None = None
    thumbnail_error: str | None = None
    comment_error: str | None = None
    channel_has_default_comment: bool = False
    thumbnail_path: str | None = None
    scheduled_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class JobSummary(BaseModel):
    job_id: str
    started_at: datetime
    total: int
    completed: int
    failed: int
    in_flight: int  # pending + uploading
    status: str  # 'running' | 'partial' | 'failed' | 'completed'
