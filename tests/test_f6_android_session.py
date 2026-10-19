"""F6.7 PWA session persistence: static guards for Android process eviction."""
from pathlib import Path

def test_cookie_remains_http_only_and_persistent():
    source=Path("app/auth/http.py").read_text()
    assert "max_age=settings.auth_session_ttl_hours * 3600" in source or "max_age = settings.auth_session_ttl_hours * 3600" in source
    assert "httponly=True" in source
    assert "samesite=\"strict\"" in source
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
