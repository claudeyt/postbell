from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.language_schedule import LanguageSchedule
from backend.schemas.language_schedule import (
    LanguageScheduleResponse,
    LanguageScheduleUpsert,
)

router = APIRouter(prefix="/api/language-schedules", tags=["language_schedules"])


@router.get("", response_model=list[LanguageScheduleResponse])
def list_schedules(db: Session = Depends(get_db)):
    return (
        db.query(LanguageSchedule)
        .order_by(LanguageSchedule.language_code.asc())
        .all()
    )


@router.put("/{lang}", response_model=LanguageScheduleResponse)
def upsert_schedule(
    lang: str, body: LanguageScheduleUpsert, db: Session = Depends(get_db)
):
    existing = (
        db.query(LanguageSchedule)
        .filter(LanguageSchedule.language_code == lang)
        .first()
    )
    if existing:
        existing.time_brt = body.time_brt
        existing.updated_at = datetime.utcnow()
        row = existing
    else:
        row = LanguageSchedule(
            language_code=lang,
            time_brt=body.time_brt,
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{lang}", status_code=204)
def delete_schedule(lang: str, db: Session = Depends(get_db)):
    existing = (
        db.query(LanguageSchedule)
        .filter(LanguageSchedule.language_code == lang)
        .first()
    )
    if not existing:
        raise HTTPException(404, "Schedule not found")
    db.delete(existing)
    db.commit()
    return None
