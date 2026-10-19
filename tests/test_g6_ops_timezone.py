"""Regression: Ops logs display Madrid wall-clock time, storage remains UTC."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

def test_ops_uses_madrid_not_utc_or_browser_timezone():
    source = Path("app/static/ops.js").read_text(encoding="utf-8")
    assert "timeZone: 'Europe/Madrid'" in source
    assert "timeZoneName: 'short'" in source
    assert "timeZone:'UTC'" not in source

def test_madrid_autumn_summer_offset():
    madrid = ZoneInfo("Europe/Madrid")
    october = datetime(2026,10,19,11,30,tzinfo=timezone.utc).astimezone(madrid)
    november = datetime(2026,11,2,11,30,tzinfo=timezone.utc).astimezone(madrid)
    assert (october.hour, october.minute)==(13,30)
    assert (november.hour, november.minute)==(12,30)
    assert october.utcoffset().total_seconds()==7200
    assert november.utcoffset().total_seconds()==3600
