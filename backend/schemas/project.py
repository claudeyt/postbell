from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    client_secret_path: str
    daily_quota_limit: int = 10000


class ProjectResponse(BaseModel):
    id: int
    name: str
    client_secret_path: str
    daily_quota_limit: int
    created_at: datetime

    model_config = {"from_attributes": True}
