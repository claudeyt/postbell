from datetime import datetime, timedelta
from unittest.mock import MagicMock

from backend.services.analytics_service import AnalyticsService


def _dates():
    """Mirror the date math in AnalyticsService.get_channel_analytics."""
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    return str(today), str(yesterday), str(day_before)


def _core_response(today_str, yesterday_str, day_before_str):
    """Synthetic core query response covering the day-before-yesterday,
    yesterday, and today.

    The "latest with data" rule should pick yesterday's row first (because
    today is skipped).
    """
    return {
        "columnHeaders": [
            {"name": "day"},
            {"name": "views"},
            {"name": "subscribersGained"},
            {"name": "subscribersLost"},
        ],
        "rows": [
            [day_before_str, 200, 99, 9],   # fallback if yesterday missing
            [yesterday_str, 100, 10, 2],    # preferred: 10 - 2 = 8
            [today_str, 40, 5, 1],          # MUST be skipped (lag)
        ],
    }


def _revenue_response(yesterday_str):
    """Synthetic revenue: one yesterday row."""
    return {
        "columnHeaders": [
            {"name": "day"},
            {"name": "estimatedRevenue"},
        ],
        "rows": [
            [yesterday_str, 1.5],
        ],
    }


def _make_analytics_mock(execute_side_effect):
    analytics = MagicMock()
    query = MagicMock()
    query.execute.side_effect = (
        execute_side_effect if isinstance(execute_side_effect, list)
        else execute_side_effect
    )
    analytics.reports.return_value.query.return_value = query
    return analytics


class _FakeResp:
    def __init__(self, status):
        self.status = status


class _FakeHttpError(Exception):
    def __init__(self, status, message="forbidden"):
        super().__init__(message)
        self.resp = _FakeResp(status)


def test_happy_path_picks_yesterday():
    today_str, yesterday_str, day_before_str = _dates()
    core = _core_response(today_str, yesterday_str, day_before_str)
    rev = _revenue_response(yesterday_str)
    analytics = _make_analytics_mock([core, rev])

    result = AnalyticsService().get_channel_analytics(analytics, "UCfake123")

    assert result["available"] is True
    assert result["error"] is None
    # views_today is dropped entirely
    assert "views_today" not in result
    # Latest 2 available days excluding today: yesterday (100) + day_before (200) = 300
    assert result["views_48h"] == 300
    assert result["views_window_dates"] == [yesterday_str, day_before_str]
    # Latest available with data, today skipped -> yesterday's row
    assert result["subscribers_last"] == 8
    assert result["subscribers_last_date"] == yesterday_str
    assert result["revenue_last"] == 1.5
    assert result["revenue_last_date"] == yesterday_str


def test_falls_back_to_day_before_when_yesterday_missing():
    """If yesterday has no subscriber data, we fall back to the latest older
    day that does have data (NOT today, which is always skipped)."""
    today_str, yesterday_str, day_before_str = _dates()
    core = {
        "columnHeaders": [
            {"name": "day"},
            {"name": "views"},
            {"name": "subscribersGained"},
            {"name": "subscribersLost"},
        ],
        "rows": [
            [day_before_str, 200, 99, 9],   # fallback target
            [today_str, 40, 5, 1],           # MUST be skipped
        ],
    }
    rev = {
        "columnHeaders": [
            {"name": "day"},
            {"name": "estimatedRevenue"},
        ],
        "rows": [
            [day_before_str, 2.75],
        ],
    }
    analytics = _make_analytics_mock([core, rev])

    result = AnalyticsService().get_channel_analytics(analytics, "UCfake123")

    assert result["subscribers_last"] == 90   # 99 - 9
    assert result["subscribers_last_date"] == day_before_str
    assert result["revenue_last"] == 2.75
    assert result["revenue_last_date"] == day_before_str


def test_revenue_empty_rows_returns_none():
    today_str, yesterday_str, day_before_str = _dates()
    core = _core_response(today_str, yesterday_str, day_before_str)
    empty_rev = {
        "columnHeaders": [
            {"name": "day"},
            {"name": "estimatedRevenue"},
        ],
        "rows": [],
    }
    analytics = _make_analytics_mock([core, empty_rev])

    result = AnalyticsService().get_channel_analytics(analytics, "UCfake123")

    assert result["available"] is True
    assert result["revenue_last"] is None
    assert result["revenue_last_date"] is None
    assert result["subscribers_last"] == 8


def test_scope_failure_path():
    analytics = _make_analytics_mock(_FakeHttpError(403))

    result = AnalyticsService().get_channel_analytics(analytics, "UCfake123")

    assert result["available"] is False
    assert "re-authenticate" in result["error"]
    assert "views_today" not in result
    assert result["views_48h"] == 0
    assert result["views_window_dates"] == []
    assert result["subscribers_last"] == 0
    assert result["subscribers_last_date"] is None
    assert result["revenue_last"] is None
    assert result["revenue_last_date"] is None


def test_views_48h_falls_back_to_one_day_when_yesterday_missing():
    """When yesterday is absent from per_day (only day_before + today exist),
    views_48h uses just day_before's views since today is excluded."""
    today_str, yesterday_str, day_before_str = _dates()
    core = {
        "columnHeaders": [
            {"name": "day"},
            {"name": "views"},
            {"name": "subscribersGained"},
            {"name": "subscribersLost"},
        ],
        "rows": [
            [day_before_str, 200, 99, 9],
            [today_str, 40, 5, 1],  # excluded from views window
        ],
    }
    rev = {
        "columnHeaders": [{"name": "day"}, {"name": "estimatedRevenue"}],
        "rows": [],
    }
    analytics = _make_analytics_mock([core, rev])

    result = AnalyticsService().get_channel_analytics(analytics, "UCfake123")

    # Only day_before is in the eligible window -> 200, single date
    assert result["views_48h"] == 200
    assert result["views_window_dates"] == [day_before_str]


def test_no_historical_data_at_all_zeroes_subscribers():
    """If only today's row exists (and we skip today), subscribers_last must be
    0 and the date None."""
    today_str, yesterday_str, day_before_str = _dates()
    core = {
        "columnHeaders": [
            {"name": "day"},
            {"name": "views"},
            {"name": "subscribersGained"},
            {"name": "subscribersLost"},
        ],
        "rows": [
            [today_str, 40, 5, 1],
        ],
    }
    rev = {
        "columnHeaders": [{"name": "day"}, {"name": "estimatedRevenue"}],
        "rows": [],
    }
    analytics = _make_analytics_mock([core, rev])

    result = AnalyticsService().get_channel_analytics(analytics, "UCfake123")

    assert result["subscribers_last"] == 0
    assert result["subscribers_last_date"] is None
    assert "views_today" not in result
    # Only today is present in per_day; today is skipped -> no window -> 0
    assert result["views_48h"] == 0
    assert result["views_window_dates"] == []
