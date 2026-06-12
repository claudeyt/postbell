from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.channel import Channel
from backend.models.channel_group import ChannelGroup
from backend.schemas.channel_group import (
    ChannelGroupCreate,
    ChannelGroupResponse,
    ChannelGroupUpdate,
    ReorderRequest,
)

router = APIRouter(prefix="/api/channel-groups", tags=["channel_groups"])


@router.get("", response_model=list[ChannelGroupResponse])
def list_groups(db: Session = Depends(get_db)):
    return (
        db.query(ChannelGroup)
        .order_by(ChannelGroup.display_order, ChannelGroup.id)
        .all()
    )


@router.post("", response_model=ChannelGroupResponse)
def create_group(body: ChannelGroupCreate, db: Session = Depends(get_db)):
    current_max = db.query(func.coalesce(func.max(ChannelGroup.display_order), -1)).scalar()
    if current_max is None:
        current_max = -1
    next_order = current_max + 1
    grp = ChannelGroup(name=body.name.strip(), display_order=next_order)
    db.add(grp)
    db.commit()
    db.refresh(grp)
    return grp


# NOTE: /reorder must be declared before /{group_id} so FastAPI doesn't try to
# coerce the literal "reorder" into an int path param.
@router.patch("/reorder")
def reorder_groups(body: ReorderRequest, db: Session = Depends(get_db)):
    for index, gid in enumerate(body.ids):
        db.query(ChannelGroup).filter(ChannelGroup.id == gid).update(
            {ChannelGroup.display_order: index}
        )
    db.commit()
    return {"updated": len(body.ids)}


@router.patch("/{group_id}", response_model=ChannelGroupResponse)
def update_group(
    group_id: int, body: ChannelGroupUpdate, db: Session = Depends(get_db)
):
    grp = db.query(ChannelGroup).filter(ChannelGroup.id == group_id).first()
    if not grp:
        raise HTTPException(404, "Group not found")
    if body.name is not None:
        grp.name = body.name.strip()
    if body.display_order is not None:
        grp.display_order = body.display_order
    db.commit()
    db.refresh(grp)
    return grp


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    grp = db.query(ChannelGroup).filter(ChannelGroup.id == group_id).first()
    if not grp:
        raise HTTPException(404, "Group not found")
    # Channels keep existing; their group_id should already be set to NULL by
    # FK ON DELETE SET NULL, but SQLite does not always enforce FK actions --
    # do it explicitly:
    db.query(Channel).filter(Channel.group_id == group_id).update(
        {Channel.group_id: None}
    )
    db.delete(grp)
    db.commit()
    return None
