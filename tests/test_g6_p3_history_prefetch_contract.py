"""P3 browser loading contract: historical prefetch may not block Home."""
from pathlib import Path


def test_dashboard_fetch_remains_first_class():
    src = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "void refreshDashboard();" in src
    assert "fetch(options.live ? '/api/dashboard?refresh=true' : '/api/dashboard'" in src
    assert "await loadAutomationStatus();" in src
    assert "scheduleHistoryPrefetch();" in src
    assert src.index("await loadAutomationStatus();") < src.index("scheduleHistoryPrefetch();")
    assert "requestIdleCallback" in src
    assert "window.setTimeout(() => { void run(); }, 1500)" in src


def test_history_and_pnl_reuse_background_requests():
    src = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "const HISTORY_PREFETCH_TTL_MS = 10 * 60 * 1000;" in src
    assert "historyReadCache.set(url, entry);" in src
    assert "if (historyReadCache.get(url) === entry) historyReadCache.delete(url);" in src
    assert "await cachedHistoryRead(`/api/history?limit=${encodeURIComponent(limit)}`)" in src
    assert "const payload = await cachedHistoryRead(url);" in src
    assert "await cachedHistoryRead('/api/history?limit=100');" in src
    assert "await cachedHistoryRead('/api/pnl/daily-cumulative?days=7');" in src


def test_pwa_script_cache_busted():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert "app.js?v=g6-history-idle-prefetch-1" in html
