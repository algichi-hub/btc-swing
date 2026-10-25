"""G6 P1 bootstrap ordering guards (no network or database)."""
from pathlib import Path


def _bootstrap():
    src = Path("app/static/app.js").read_text(encoding="utf-8")
    return src[src.index("async function bootstrap()"):src.index("\nbootstrap();", src.index("async function bootstrap()"))]


def test_auth_and_csrf_started_concurrently():
    src = _bootstrap()
    assert src.index("const csrfPromise = fetchCsrfToken();") < src.index("const user = await checkAuth();")
    assert "await fetchCsrfToken();" not in src


def test_dashboard_starts_after_auth_but_without_csrf_wait():
    src = _bootstrap()
    assert src.index("if (!user)") < src.index("void refreshDashboard();")
    assert src.index("void refreshDashboard();") < src.index("const hashView =")
    assert "await csrfPromise" not in src


def test_mutating_controls_require_resolved_csrf_token():
    src = _bootstrap()
    block = src[src.index("void csrfPromise.then((token) => {"):src.index("  attachTradeDiagnosticsToggle();")]
    assert "if (!token)" in block
    for handler in (
        "attachSettingsForm();",
        "attachPasswordChange();",
        "attachRecoveryCodes();",
        "attachTelegramTestButton();",
        "attachDatabaseReset();",
    ):
        assert block.index(handler) > block.index("if (!token)")


def test_new_client_script_cache_version():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert "app.js?v=g6-parallel-auth-csrf-1" in html
