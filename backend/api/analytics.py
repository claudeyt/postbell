import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.account import Account
from backend.models.channel import Channel
from backend.schemas.analytics import (
    AnalyticsAverages,
    AnalyticsSummaryResponse,
    ChannelAnalytics,
)
from backend.services.analytics_service import analytics_service
from backend.services.oauth_service import oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

NOTE = (
    "YouTube Analytics has a 1-2 day reporting delay, so subscriber and revenue "
    "figures reflect yesterday's data. Revenue is best-effort and only available "
    "for monetized channels. If all channels show unavailable, re-authenticate "
    "your accounts to grant the analytics scopes."
)


def _parse_channel_ids(channel_ids: str | None) -> list[int] | None:
    """Parse comma-separated DB channel ids. Returns None to mean 'all channels'."""
    if not channel_ids or not channel_ids.strip():
        return None
    ids: list[int] = []
    for part in channel_ids.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    channel_ids: str = "", db: Session = Depends(get_db)
) -> AnalyticsSummaryResponse:
    """Return per-channel YouTube Analytics plus the average across selected channels.

    `channel_ids` is a comma-separated list of DB channel ids (e.g. "1,2,3").
    If omitted/empty, all channels are used. Always returns HTTP 200, even when
    every channel is unavailable (e.g. missing analytics scope).
    """
    requested_ids = _parse_channel_ids(channel_ids)
    if requested_ids is None:
        channels = db.query(Channel).all()
    else:
        channels = (
            db.query(Channel).filter(Channel.id.in_(requested_ids)).all()
            if requested_ids
            else []
        )

    results: list[ChannelAnalytics] = []
    for channel in channels:
        try:
            account = (
                db.query(Account).filter(Account.id == channel.account_id).first()
            )
            creds = (
                oauth_service.load_credentials(account.token_path)
                if account
                else None
            )
            if creds is None:
                results.append(
                    ChannelAnalytics(
                        channel_id=channel.id,
                        channel_name=channel.channel_name,
                        available=False,
                        error="no credentials",
                        views_48h=0,
                        views_window_dates=[],
                        subscribers_last=0,
                        subscribers_last_date=None,
                        revenue_last=None,
                        revenue_last_date=None,
                    )
                )
                continue

            analytics = oauth_service.get_analytics_service(creds)
            metrics = analytics_service.get_channel_analytics(
                analytics, channel.channel_id
            )
            results.append(
                ChannelAnalytics(
                    channel_id=channel.id,
                    channel_name=channel.channel_name,
                    available=metrics["available"],
                    error=metrics["error"],
                    views_48h=metrics["views_48h"],
                    views_window_dates=metrics.get("views_window_dates", []),
                    subscribers_last=metrics["subscribers_last"],
                    subscribers_last_date=metrics["subscribers_last_date"],
                    revenue_last=metrics["revenue_last"],
                    revenue_last_date=metrics["revenue_last_date"],
                )
            )
        except Exception as exc:  # noqa: BLE001 — one bad channel must not 500 the endpoint
            logger.warning(
                "Failed to resolve analytics for channel %s: %s", channel.id, exc
            )
            results.append(
                ChannelAnalytics(
                    channel_id=channel.id,
                    channel_name=channel.channel_name,
                    available=False,
                    error=f"unexpected error: {exc}",
                    views_48h=0,
                    views_window_dates=[],
                    subscribers_last=0,
                    subscribers_last_date=None,
                    revenue_last=None,
                    revenue_last_date=None,
                )
            )

    averages = _compute_averages(results)
    return AnalyticsSummaryResponse(channels=results, averages=averages, note=NOTE)


def _compute_averages(results: list[ChannelAnalytics]) -> AnalyticsAverages:
    """Average across only the channels where available=True."""
    available = [r for r in results if r.available]
    count = len(available)
    if count == 0:
        return AnalyticsAverages(
            views_48h=0.0,
            subscribers_last=0.0,
            revenue_last=None,
            channel_count=0,
        )

    avg_views_48h = sum(r.views_48h for r in available) / count
    avg_subscribers_last = sum(r.subscribers_last for r in available) / count

    revenue_values = [
        r.revenue_last for r in available if r.revenue_last is not None
    ]
    avg_revenue = (
        sum(revenue_values) / len(revenue_values) if revenue_values else None
    )

    return AnalyticsAverages(
        views_48h=avg_views_48h,
        subscribers_last=avg_subscribers_last,
        revenue_last=avg_revenue,
        channel_count=count,
    )
