"""F6.7 PWA session persistence: static guards for Android process eviction."""
from pathlib import Path

def test_cookie_remains_http_only_and_persistent():
    source=Path("app/auth/http.py").read_text()
    assert "max_age=settings.auth_session_ttl_hours * 3600" in source or "max_age = settings.auth_session_ttl_hours * 3600" in source
    assert "httponly=True" in source
    assert "samesite=\"lax\"" in source
    assert "secure=settings.auth_cookie_secure" in source

def test_pwa_reconnect_does_not_evict_session():
    source=Path("app/static/app.js").read_text()
    start=source.index("async function checkAuth()")
    end=source.index("let currentCsrfToken",start)
    method=source[start:end]
    assert "credentials: 'same-origin'" in method
    assert "res.status === 401 || res.status === 403" in method
    assert "Reintentar conexión" in method
    assert "window.location.href = '/login'" not in method
    assert "window.location.replace('/login')" in method

def test_30_day_default_and_no_password_storage():
    source=Path("app/config.py").read_text()
    assert 'AUTH_SESSION_TTL_HOURS", 720' in source
    auth=Path("app/static/login.js").read_text()
    assert "localStorage.setItem" not in auth
    assert "sessionStorage.setItem" not in auth


def test_auth_probe_owns_redirect_and_does_not_race_global_401_interceptor():
    source = Path("app/static/app.js").read_text()
    global_interceptor = source.split("const DEFAULT_REFRESH_MS", 1)[0]
    assert "!url.includes('/api/auth/me')" in global_interceptor
    probe = source[source.index("async function checkAuth()"):source.index("let currentCsrfToken")]
    assert "res.status === 401 || res.status === 403" in probe
    assert "window.location.replace('/login')" in probe
    assert "if (!res.ok)" in probe
    assert "showReconnect();" in probe


def test_session_cookie_has_30_day_duration_not_session_only():
    from fastapi import Response
    from app.auth.http import set_session_cookie, delete_session_cookie
    from app.config import settings

    response = Response()
    set_session_cookie(response, "test-token")
    cookie = response.headers["set-cookie"]
    assert "httponly" in cookie.lower()
    assert "max-age=" + str(settings.auth_session_ttl_hours * 3600) in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    assert ("secure" in cookie.lower()) == settings.auth_cookie_secure
    logout = Response()
    delete_session_cookie(logout)
    assert "max-age=0" in logout.headers["set-cookie"].lower()
