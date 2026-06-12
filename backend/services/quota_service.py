from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.models.account import Account
from backend.models.channel import Channel
from backend.models.quota import QuotaUsage
from backend.models.project import Project
from backend.models.upload import Upload
from backend.schemas.quota import QuotaSummaryItem


# YouTube quota and the daily video cap both reset at midnight Pacific Time.
# We use America/Los_Angeles so DST transitions are handled correctly.
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")

# Hardcoded daily uploads-dispatched cap, per project.
DAILY_VIDEO_LIMIT = 100


def _pacific_today() -> date:
    """Current calendar date in YouTube's reset timezone (America/Los_Angeles)."""
    return datetime.now(PACIFIC_TZ).date()


class QuotaService:
    def record_usage(self, project_id: int, units: int, db: Session) -> QuotaUsage:
        """Add units to today's quota_usage record (upsert).

        "Today" is anchored to YouTube's reset boundary (Pacific midnight) so
        the counter flips at the same instant YouTube actually resets us.
        """
        today = _pacific_today().isoformat()
        record = (
            db.query(QuotaUsage)
            .filter(QuotaUsage.project_id == project_id, QuotaUsage.date == today)
            .first()
        )
        if record:
            record.units_used += units
        else:
            record = QuotaUsage(project_id=project_id, date=today, units_used=units)
            db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get_daily_usage(self, project_id: int, day: date, db: Session) -> int:
        """Return units used for a specific day."""
        day_str = day.isoformat()
        record = (
            db.query(QuotaUsage)
            .filter(QuotaUsage.project_id == project_id, QuotaUsage.date == day_str)
            .first()
        )
        return record.units_used if record else 0

    def _videos_today_for_project(self, project_id: int, db: Session) -> int:
        """Count Upload rows whose channel's account belongs to ``project_id`` and
        whose ``created_at`` falls inside today's Pacific calendar day.

        Counts ALL statuses (pending/uploading/completed/failed). The cap is a
        cap on dispatched attempts, not successful uploads -- this mirrors the
        quota fix where we charge on dispatch, not on success.
        """
        today_pacific = _pacific_today()
        # Build the [start, end) UTC window for "today in Pacific".
        start_pacific = datetime.combine(today_pacific, time.min, tzinfo=PACIFIC_TZ)
        end_pacific = start_pacific.replace(hour=23, minute=59, second=59, microsecond=999999)
        # Upload.created_at is stored as a naive UTC datetime (default=datetime.utcnow),
        # so compare against naive-UTC bounds.
        start_utc = start_pacific.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_utc = end_pacific.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        return (
            db.query(Upload)
            .join(Channel, Upload.channel_id == Channel.id)
            .join(Account, Channel.account_id == Account.id)
            .filter(Account.project_id == project_id)
            .filter(Upload.created_at >= start_utc)
            .filter(Upload.created_at <= end_utc)
            .count()
        )

    def get_summary(self, db: Session) -> list[QuotaSummaryItem]:
        """Return per-project summary: name, daily_quota_limit, units_used_today,
        remaining, plus the new videos_today / video_limit counters.
        """
        today = _pacific_today().isoformat()
        projects = db.query(Project).all()
        result: list[QuotaSummaryItem] = []
        for project in projects:
            usage = (
                db.query(QuotaUsage)
                .filter(QuotaUsage.project_id == project.id, QuotaUsage.date == today)
                .first()
            )
            units_used = usage.units_used if usage else 0
            remaining = max(0, project.daily_quota_limit - units_used)
            percentage_used = (
                round(units_used / project.daily_quota_limit * 100, 2)
                if project.daily_quota_limit > 0
                else 0.0
            )
            videos_today = self._videos_today_for_project(project.id, db)
            result.append(
                QuotaSummaryItem(
                    project_id=project.id,
                    project_name=project.name,
                    daily_limit=project.daily_quota_limit,
                    units_used=units_used,
                    remaining=remaining,
                    percentage_used=percentage_used,
                    videos_today=videos_today,
                    video_limit=DAILY_VIDEO_LIMIT,
                )
            )
        return result

    def estimate_cost(self, num_videos: int, has_thumbnail: bool) -> int:
        """Return estimated units: 100 per video + 50 per thumbnail."""
        cost = num_videos * 100
        if has_thumbnail:
            cost += 50
        return cost


quota_service = QuotaService()
