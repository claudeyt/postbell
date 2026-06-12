from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChannelGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ChannelGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    display_order: int | None = None


class ChannelGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_order: int
    created_at: datetime


class ReorderRequest(BaseModel):
    ids: list[int]
    group_id: int | None = None  # only used for channel reorder; ignored on group reorder
