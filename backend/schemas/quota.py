from pydantic import BaseModel


class QuotaEstimateRequest(BaseModel):
    file_count: int
    has_thumbnail: bool = False


class QuotaEstimateResponse(BaseModel):
    estimated_cost: int
    remaining_quota: int
    sufficient: bool


class QuotaSummaryItem(BaseModel):
    project_id: int
    project_name: str
    daily_limit: int
    units_used: int
    remaining: int
    percentage_used: float
    videos_today: int
    video_limit: int


class QuotaSummaryResponse(BaseModel):
    projects: list[QuotaSummaryItem]
