from pathlib import Path


def test_queue_requires_admin_csrf_and_dashboard_remains_read_only():
    main = Path("app/main.py").read_text(encoding="utf-8")
    start = main.index('@admin_router.post("/engine/manual-refresh")')
    end = main.index('@viewer_router.get("/dashboard")', start)
    block = main[start:end]
    assert "INSERT INTO manual_cycle_requests" in block
    assert "run_market_cycle" not in block
    assert "build_dashboard_payload" not in block
    assert "uuid.uuid4()" in block
    assert '@viewer_router.get("/engine/manual-refresh/{request_id}")' in block
    assert "Depends(require_admin), Depends(verify_csrf_token)" in main
    dashboard = main[end:main.index('@viewer_router.get("/history")',end)]
    assert "trade_repository.get_latest_engine_snapshot()" in dashboard


def test_ui_uses_manual_worker_queue_and_neon_timestamp():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "fetch('/api/engine/manual-refresh', { method: 'POST', headers: getCsrfHeaders()" in js
    assert "'/api/engine/manual-refresh/' + encodeURIComponent(id)" in js
    assert "if (state.status !== 'OK') continue;" in js
    assert "Datos: ${formatDashboardDataTime(state.snapshot_at)} (actualizado)" in js
    assert "Datos: ${formatDashboardDataTime(payload.snapshot_created_at || payload.timestamp)} (Neon)" in js
    assert "timeZone: 'Europe/Madrid'" in js
    assert "manualRefreshBtn.disabled = true;" in js
    assert "fetch(options.live ? '/api/dashboard?refresh=true'" not in js
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert 'id="status" class="hidden"' in html
    assert "app.js?v=g6-engine-manual-cycle-2" in html
