"""Contract regression for 1h candle-direction coloring (not buy/sell delta)."""
from pathlib import Path


def test_volume_contract_preserves_total_and_adds_direction():
    src = Path("app/strategy/dashboard.py").read_text()
    start = src.index("def compute_volume_24h_hourly(")
    end = src.index("\ndef compute_position_pct(", start)
    scope = src[start:end]
    assert '"volume_btc": round(candle.volume, 8)' in scope
    assert '"volume_usd": round(candle.volume * candle.close, 2)' in scope
    assert '"candle_direction": "UP" if candle.close > candle.open else ("DOWN" if candle.close < candle.open else "FLAT")' in scope
    assert "candle.volume" in scope
    assert "aggressor" not in scope and "net_volume" not in scope


def test_frontend_direction_and_unknown_snapshot_fallback():
    src = Path("app/static/app.js").read_text()
    assert "['UP', 'DOWN', 'FLAT'].includes(bar.candle_direction)" in src
    assert "'UNKNOWN'" in src
    assert "hourly-volume-bar--${direction.toLowerCase()}" in src
    assert src.index("const tooltipTime = formatTimeFromIso(bar.timestamp);") < src.index("barElement.setAttribute('aria-label',")
    css = Path("app/static/styles.css").read_text()
    for direction in ("up", "down", "flat", "unknown"):
        assert ".hourly-volume-bar--" + direction in css


def test_disclaimer_and_asset_version():
    html = Path("app/static/index.html").read_text()
    assert "no representa compras/ventas netas" in html
    assert "app.js?v=g6-volume-candle-direction-1" in html
