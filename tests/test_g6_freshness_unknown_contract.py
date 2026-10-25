from pathlib import Path


def test_unknown_and_stale_are_distinct_but_fail_closed():
    source = Path("app/main.py").read_text(encoding="utf-8")
    start = source.index('@viewer_router.get("/dashboard")')
    end = source.index('@viewer_router.get("/history")', start)
    block = source[start:end]
    assert 'freshness_status = "STALE" if not snapshot_fresh' in block
    assert 'else "UNKNOWN"' in block
    assert 'payload["market_freshness"] = {"status": freshness_status, "is_stale": True' in block
    assert 'payload["signal"] = {"state": "NO_TRADE", "side": None}' in block
    assert 'payload["trade_plan"] = None' in block
    assert 'payload["potential_trade_plan"] = None' in block


def test_status_displays_unknown_without_claiming_online():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "marketFreshness?.status === 'STALE' ? 'DATOS DE MERCADO OBSOLETOS' : 'FRESCURA NO VERIFICADA'" in source
    assert "const freshMarket = marketFreshness?.status === 'FRESH' && marketFreshness?.is_stale === false;" in source
    assert "Señales bloqueadas · sin verificación de la última vela 1h" in source
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert "app.js?v=g6-freshness-status-1" in html
