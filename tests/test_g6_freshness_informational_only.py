from pathlib import Path


def test_snapshot_freshness_is_informational_only():
    src = Path("app/main.py").read_text(encoding="utf-8")
    block = src.split('@viewer_router.get("/dashboard")', 1)[1].split('@viewer_router.get("/history")', 1)[0]
    assert 'payload["snapshot_stale"] = not snapshot_fresh' in block
    assert 'payload["market_freshness"]' in block
    for field in ('signal', 'trade_plan', 'potential_trade_plan'):
        assert f'payload["{field}"] =' not in block


def test_client_always_displays_engine_signals():
    src = Path("app/static/app.js").read_text(encoding="utf-8")
    start = src.index('const marketFreshness = payload.market_freshness;')
    end = src.index('renderTradeDiagnostics(', start)
    section = src[start:end]
    assert 'renderSignal(payload.signal || {});' in section
    assert 'renderTradePlan(payload.signal?.state, payload.trade_plan, payload.potential_trade_plan);' in section
    assert "freshMarket ?" not in section
    assert 'NO_TRADE' not in section


def test_freshness_message_does_not_claim_trading_is_blocked():
    src = Path("app/static/app.js").read_text(encoding="utf-8")
    section = src.split('const marketFreshness = payload.market_freshness;', 1)[1].split('scheduleHistoryPrefetch();', 1)[0]
    assert 'Señales bloqueadas' not in section
    assert 'Frescura de vela 1h no verificada' in section
