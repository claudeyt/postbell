from pydantic import BaseModel


class ChannelAnalytics(BaseModel):
    channel_id: int
    channel_name: str
    available: bool
    error: str | None
    views_48h: int
    views_window_dates: list[str] = []
    subscribers_last: int
    subscribers_last_date: str | None
    revenue_last: float | None
    revenue_last_date: str | None


class AnalyticsAverages(BaseModel):
    views_48h: float
    subscribers_last: float
    revenue_last: float | None
    channel_count: int


class AnalyticsSummaryResponse(BaseModel):
    channels: list[ChannelAnalytics]
    averages: AnalyticsAverages
    note: str
