from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.quota import (
    QuotaEstimateRequest,
    QuotaEstimateResponse,
    QuotaSummaryItem,
    QuotaSummaryResponse,
)
from backend.services.quota_service import quota_service

router = APIRouter(prefix="/api/quota", tags=["quota"])


@router.get("/summary", response_model=QuotaSummaryResponse)
def get_quota_summary(db: Session = Depends(get_db)):
    """Return per-project quota usage summary for today."""
    items: list[QuotaSummaryItem] = quota_service.get_summary(db)
    return QuotaSummaryResponse(projects=items)


@router.post("/estimate", response_model=QuotaEstimateResponse)
def estimate_quota(req: QuotaEstimateRequest, db: Session = Depends(get_db)):
    """Estimate quota cost for a given number of videos."""
    estimated_cost = quota_service.estimate_cost(req.file_count, req.has_thumbnail)
    summary = quota_service.get_summary(db)
    total_remaining = sum(item.remaining for item in summary)
    return QuotaEstimateResponse(
        estimated_cost=estimated_cost,
        remaining_quota=total_remaining,
        sufficient=total_remaining >= estimated_cost,
    )
