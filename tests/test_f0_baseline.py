"""F0 safe, offline baseline checks for the original V4 source artifact.

These tests never start FastAPI, Telegram, network I/O or the trading scheduler.
"""
import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY_FILES = sorted((ROOT / 'app').rglob('*.py'))


def test_python_sources_parse():
    assert len(PY_FILES) >= 30
    for path in PY_FILES:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def test_no_order_sender_in_v4_sources():
    """Static inventory: warrants follow-up when new outward-facing paths appear."""
    forbidden = ('exchange.order(', '.place_order(', '/exchange', 'send_order(', 'submit_order(')
    for path in PY_FILES:
        if path.name == 'test_f0_baseline.py':
            continue
        src = path.read_text(encoding='utf-8').lower()
        assert not any(marker in src for marker in forbidden), str(path)


def test_telegram_request_is_only_outbound_post_in_original_source():
    sites = []
    for path in PY_FILES:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {'post', 'put', 'delete', 'patch'}:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'requests':
                    sites.append((path.relative_to(ROOT).as_posix(), node.func.attr))
    assert sites == [('app/notifications/telegram.py', 'post')]


def test_production_config_rejects_insecure_cookies():
    from dataclasses import replace
    from app.config import Settings
    with pytest.raises(ValueError, match='AUTH_COOKIE_SECURE'):
        replace(Settings(), app_env='production', auth_cookie_secure=False).validate_runtime()


def test_production_config_rejects_wildcard_origins():
    from dataclasses import replace
    from app.config import Settings
    with pytest.raises(ValueError, match='AUTH_ALLOWED_ORIGINS'):
        replace(Settings(), app_env='production', auth_cookie_secure=True,
                auth_allowed_origins=('*',), auth_csrf_secret=__import__('base64').urlsafe_b64encode(b'Z'*32).decode()).validate_runtime()


def test_passwords_are_argon2_and_session_tokens_random():
    from app.auth.security import hash_password, verify_password, generate_session_token
    pw = 'long-unique-passphrase-42'
    digest = hash_password(pw)
    assert digest.startswith('$argon2id$')
    assert verify_password(pw, digest)
    assert not verify_password('wrong', digest)
    assert generate_session_token() != generate_session_token()


def test_algorithm_default_volume_threshold_stays_fixed():
    from app.config import Settings
    assert Settings().volume_confirmation_threshold == 1.05


def test_telegrams_disabled_by_default():
    from app.config import Settings
    assert Settings().telegram_enabled is False


def test_scheduler_interval_declared_300_seconds():
    src = (ROOT / 'app/automation/scheduler.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    values = {target.id:node.value.value for node in tree.body if isinstance(node, ast.Assign)
              for target in node.targets if isinstance(target, ast.Name)
              if isinstance(node.value, ast.Constant)}
    assert values['MARKET_CYCLE_INTERVAL_SECONDS'] == 300


def test_source_static_frontend_has_no_remote_executable_script():
    htmls = (ROOT/'app/static').glob('*.html')
    for path in htmls:
        html = path.read_text(encoding='utf-8').lower()
        assert not re.search(r'<script[^>]+src=[\"\']https?://', html), str(path)


def test_auth_default_secret_is_not_accepted_as_production_policy():
    """Document known V4 defect as expected failure until mitigation exists."""
    from dataclasses import replace
    from app.config import Settings
    default = Settings().auth_csrf_secret
    config = replace(Settings(), app_env='production', auth_cookie_secure=True,
                     auth_allowed_origins=('https://example.com',),
                     auth_allowed_hosts=('example.com',), auth_csrf_secret=default)
    with pytest.raises(ValueError, match='AUTH_CSRF_SECRET'):
        config.validate_runtime()
