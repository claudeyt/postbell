from datetime import datetime, timezone
from backend.services.upload_manager import _format_publish_at


def test_format_publish_at_naive_treated_as_utc():
    dt = datetime(2026, 6, 6, 19, 30, 0)
    out = _format_publish_at(dt)
    assert out == "2026-06-06T19:30:00.0Z"


def test_format_publish_at_aware_utc():
    dt = datetime(2026, 6, 6, 19, 30, 0, tzinfo=timezone.utc)
    out = _format_publish_at(dt)
    assert out == "2026-06-06T19:30:00.0Z"


def test_format_publish_at_aware_other_tz_converted_to_utc():
    from datetime import timedelta
    brt = timezone(timedelta(hours=-3))
    dt = datetime(2026, 6, 6, 16, 30, 0, tzinfo=brt)
    out = _format_publish_at(dt)
    assert out == "2026-06-06T19:30:00.0Z"


def test_format_publish_at_none():
    assert _format_publish_at(None) is None
