import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AnalyticsService:
    def get_channel_analytics(self, analytics, youtube_channel_id: str) -> dict:
        """Fetch per-channel YouTube Analytics.

        Because YouTube Analytics has a 1-2 day reporting delay, we surface the
        LATEST AVAILABLE day's data for subscribers and revenue (not strictly
        yesterday) so the user always sees real numbers — typically that's
        yesterday, but can be older when the lag is longer. Each metric is
        accompanied by its source date so the UI can label it accurately.

        `views_48h` uses the LATEST 2 AVAILABLE days excluding today, since
        YouTube's reporting lag means today (and frequently yesterday) is 0.

        `analytics` is a built youtubeAnalytics v2 service. Degrades gracefully:
        never raises — returns available=False with an error string when the
        analytics scope is missing or any API error occurs.
        """
        today = datetime.utcnow().date()
        seven_days_ago = today - timedelta(days=7)
        yesterday = today - timedelta(days=1)
        today_str = str(today)

        # QUERY 1 — core metrics (views + subscribers) across a 7-day window so
        # we can pick the latest day with actual data.
        try:
            response = (
                analytics.reports()
                .query(
                    ids=f"channel=={youtube_channel_id}",
                    startDate=str(seven_days_ago),
                    endDate=str(today),
                    metrics="views,subscribersGained,subscribersLost",
                    dimensions="day",
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — must never propagate
            error = self._classify_error(exc)
            logger.warning(
                "Analytics core query failed for channel %s: %s",
                youtube_channel_id,
                exc,
            )
            return {
                "available": False,
                "error": error,
                "views_48h": 0,
                "views_window_dates": [],
                "subscribers_last": 0,
                "subscribers_last_date": None,
                "revenue_last": None,
                "revenue_last_date": None,
            }

        headers = [h["name"] for h in response.get("columnHeaders", [])]
        rows = response.get("rows", []) or []
        per_day: dict[str, dict] = {}
        for row in rows:
            record = dict(zip(headers, row))
            day = record.get("day")
            if day is not None:
                per_day[str(day)] = record

        # Latest 2 available days, excluding today (which is always lagged 0)
        window_dates = sorted(
            [d for d in per_day.keys() if d != today_str],
            reverse=True,
        )[:2]
        views_48h = sum(int(per_day[d].get("views") or 0) for d in window_dates)

        # Net subscribers — pick the latest day in the window that has at least
        # one subscriber-related value reported. We deliberately ignore today
        # since YouTube's lag means today is almost always missing/zero by the
        # time we ask.
        subscribers_last = 0
        subscribers_last_date: str | None = None
        for day_key in sorted(per_day.keys(), reverse=True):
            if day_key == today_str:
                continue
            rec = per_day[day_key]
            gained_raw = rec.get("subscribersGained")
            lost_raw = rec.get("subscribersLost")
            if gained_raw is None and lost_raw is None:
                continue
            subscribers_last = int(gained_raw or 0) - int(lost_raw or 0)
            subscribers_last_date = day_key
            break

        # QUERY 2 — revenue across the same window. Separate try/except so its
        # failure (not monetized / missing monetary scope) never affects query 1.
        revenue_last: float | None = None
        revenue_last_date: str | None = None
        try:
            rev_response = (
                analytics.reports()
                .query(
                    ids=f"channel=={youtube_channel_id}",
                    startDate=str(seven_days_ago),
                    endDate=str(yesterday),  # skip today — never reported
                    metrics="estimatedRevenue",
                    dimensions="day",
                )
                .execute()
            )
            rev_headers = [h["name"] for h in rev_response.get("columnHeaders", [])]
            rev_rows = rev_response.get("rows", []) or []
            if rev_rows:
                # API returns rows sorted by day ASC; the latest is the last one.
                last_record = dict(zip(rev_headers, rev_rows[-1]))
                revenue_last = float(last_record.get("estimatedRevenue") or 0.0)
                day_val = last_record.get("day")
                revenue_last_date = str(day_val) if day_val is not None else None
            # No rows => stay None (not monetized OR lag hasn't resolved yet).
        except Exception as exc:  # noqa: BLE001 — revenue is optional
            logger.info(
                "Revenue query unavailable for channel %s (likely not monetized "
                "or missing monetary scope): %s",
                youtube_channel_id,
                exc,
            )
            revenue_last = None
            revenue_last_date = None

        return {
            "available": True,
            "error": None,
            "views_48h": views_48h,
            "views_window_dates": window_dates,
            "subscribers_last": subscribers_last,
            "subscribers_last_date": subscribers_last_date,
            "revenue_last": revenue_last,
            "revenue_last_date": revenue_last_date,
        }

    def _classify_error(self, exc: Exception) -> str:
        """Best-effort classification of a failed core analytics query."""
        status = getattr(getattr(exc, "resp", None), "status", None)
        if status in (401, 403):
            return "analytics scope not granted - re-authenticate"
        message = str(exc).lower()
        if "scope" in message or "insufficient" in message or "permission" in message:
            return "analytics scope not granted - re-authenticate"
        return f"analytics unavailable: {exc}"


analytics_service = AnalyticsService()
