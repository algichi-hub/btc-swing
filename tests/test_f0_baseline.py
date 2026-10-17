"""F0 static/offline verification: does not start scheduler or send HTTP requests."""
import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "app").rglob("*.py"))


def test_f0_python_sources_parse():
    assert len(SOURCES) >= 30, "V4 sources not yet imported"
    for path in SOURCES:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_f0_no_obvious_order_senders():
    forbidden = ("exchange.order(", ".place_order(", "/exchange", "send_order(", "submit_order(")
    for path in SOURCES:
        src = path.read_text(encoding="utf-8").lower()
        assert not any(x in src for x in forbidden), path


def test_f0_requests_post_inventory():
    sites = []
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"post", "put", "delete", "patch"}:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "requests":
                        sites.append((path.relative_to(ROOT).as_posix(), node.func.attr))
    assert sites == [("app/notifications/telegram.py", "post")]


def test_f0_reject_insecure_production_cookie():
    from dataclasses import replace
    from app.config import Settings
    with pytest.raises(ValueError, match="AUTH_COOKIE_SECURE"):
        replace(Settings(), app_env="production", auth_cookie_secure=False).validate_runtime()


def test_f0_reject_default_production_csrf_secret():
    from dataclasses import replace
    from app.config import Settings
    s = Settings()
    with pytest.raises(ValueError, match="AUTH_CSRF_SECRET"):
        replace(s, app_env="production", auth_cookie_secure=True,
                auth_allowed_origins=("https://example.com",),
                auth_allowed_hosts=("example.com",)).validate_runtime()


def test_f0_reject_wildcard_production_origins():
    from dataclasses import replace
    from base64 import urlsafe_b64encode
    from app.config import Settings
    with pytest.raises(ValueError, match="AUTH_ALLOWED_ORIGINS"):
        replace(Settings(), app_env="production", auth_cookie_secure=True,
                auth_allowed_origins=("*",),
                auth_csrf_secret=urlsafe_b64encode(b"Z" * 32).decode()).validate_runtime()


def test_f0_argon2_and_tokens():
    from app.auth.security import hash_password, verify_password, generate_session_token
    hashed = hash_password("unique-test-password-42")
    assert hashed.startswith("$argon2id$")
    assert verify_password("unique-test-password-42", hashed)
    assert not verify_password("incorrect", hashed)
    assert generate_session_token() != generate_session_token()


def test_f0_strategy_constants():
    from app.config import Settings
    assert Settings().volume_confirmation_threshold == 1.05
    assert Settings().telegram_enabled is False


def test_f0_market_cycle_interval():
    tree = ast.parse((ROOT / "app/automation/scheduler.py").read_text(encoding="utf-8"))
    found = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "MARKET_CYCLE_INTERVAL_SECONDS" for t in node.targets)
             and isinstance(node.value, ast.Constant)]
    assert found == [300]


def test_f0_frontend_no_remote_script():
    for path in (ROOT / "app/static").glob("*.html"):
        assert not re.search(r'<script[^>]+src=["\']https?://', path.read_text(encoding="utf-8").lower())
