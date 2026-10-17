"""Security regression for password recovery without email."""
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import service as auth_module
from app.auth.http import get_auth_service, get_current_session_and_user, verify_csrf_token
from app.auth.security import verify_password
from app.storage.database import SCHEMA
from app.main import public_router


@pytest.fixture
def recovery_fixture(tmp_path, monkeypatch):
    path = tmp_path / "recovery.sqlite"
    with sqlite3.connect(path) as con:
        con.executescript(SCHEMA)
        con.executescript((Path(__file__).resolve().parents[1] /
                           "migrations/0003_recovery_codes.sql").read_text())

    def conn_factory(_path):
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    monkeypatch.setattr(auth_module, "connect", conn_factory)
    service = auth_module.AuthService(db_path=path)
    user = service.create_user("admin", "old-password-of-sufficient-length")
    return service, user, path


def test_codes_are_unrecoverable_and_usable_once(recovery_fixture):
    service, user, path = recovery_fixture
    assert service.recovery_codes_remaining(user.id) == 0
    assert service.generate_recovery_codes(user.id, "wrong") is None
    codes = service.generate_recovery_codes(user.id, "old-password-of-sufficient-length")
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(len(code.replace("-", "")) == 32 for code in codes)
    with sqlite3.connect(path) as con:
        db_rows = con.execute("SELECT code_hash FROM auth_recovery_codes").fetchall()
    assert len(db_rows) == 10
    assert all(code.replace("-", "") not in str(db_rows) for code in codes)
    _, token = service.create_session(user.id)
    assert service.reset_password_with_code("admin", codes[0], "new-password-of-sufficient-length", "127.0.0.1") == "OK"
    assert service.validate_session(token) is None
    assert service.authenticate("admin", "old-password-of-sufficient-length") is None
    assert service.authenticate("admin", "new-password-of-sufficient-length") is not None
    assert service.recovery_codes_remaining(user.id) == 9
    assert service.reset_password_with_code("admin", codes[0], "another-long-enough-password", "127.0.0.2") == "INVALID"
    assert service.authenticate("admin", "new-password-of-sufficient-length") is not None


def test_regeneration_revokes_earlier_codes(recovery_fixture):
    service, user, _ = recovery_fixture
    first = service.generate_recovery_codes(user.id, "old-password-of-sufficient-length")
    second = service.generate_recovery_codes(user.id, "old-password-of-sufficient-length")
    assert set(first).isdisjoint(second)
    assert service.recovery_codes_remaining(user.id) == 10
    assert service.reset_password_with_code("admin", first[0], "new-password-of-sufficient-length", "10.1.1.1") == "INVALID"
    assert service.reset_password_with_code("admin", second[0], "new-password-of-sufficient-length", "10.1.1.2") == "OK"


def test_wrong_codes_are_limited_and_account_existence_not_disclosed(recovery_fixture):
    service, user, _ = recovery_fixture
    code = "eeeeeeee-eeeeeeee-eeeeeeee-eeeeeeee"
    for idx in range(5):
        assert service.reset_password_with_code("admin", code, "new-password-of-sufficient-length", "192.0.2.10") == "INVALID"
    assert service.reset_password_with_code("admin", code, "new-password-of-sufficient-length", "192.0.2.10") == "LOCKED"
    assert service.reset_password_with_code("nonexistent", code, "new-password-of-sufficient-length", "192.0.2.20") == "INVALID"
    assert service.authenticate("admin", "old-password-of-sufficient-length") is not None


def test_recovery_endpoints_session_and_csrf(recovery_fixture, monkeypatch):
    from app.config import settings
    service, user, _ = recovery_fixture
    app = FastAPI()
    app.include_router(public_router)
    app.dependency_overrides[get_auth_service] = lambda: service
    client = TestClient(app)
    origin = settings.auth_allowed_origins[0]
    payload = {"current_password": "old-password-of-sufficient-length"}
    assert client.get("/api/auth/recovery-codes/status").status_code == 401
    assert client.post("/api/auth/recovery-codes", json=payload).status_code == 403
    assert client.post("/api/auth/recovery-codes", json=payload, headers={"Origin": origin}).status_code == 401
    _, raw = service.create_session(user.id)
    session_user = service.validate_session(raw)
    app.dependency_overrides[get_current_session_and_user] = lambda: session_user
    assert client.post("/api/auth/recovery-codes", json=payload, headers={"Origin": origin}).status_code == 403
    app.dependency_overrides[verify_csrf_token] = lambda: None
    generated = client.post("/api/auth/recovery-codes", json=payload, headers={"Origin": origin})
    assert generated.status_code == 200
    assert generated.headers["cache-control"] == "no-store"
    assert len(generated.json()["codes"]) == 10
    assert client.get("/api/auth/recovery-codes/status").json()["remaining"] == 10
    invalid_origin = client.post("/api/auth/recover", json={
        "username": "admin", "recovery_code": generated.json()["codes"][0],
        "new_password": "new-password-of-sufficient-length",
    })
    assert invalid_origin.status_code == 403
    successful = client.post("/api/auth/recover", json={
        "username": "admin", "recovery_code": generated.json()["codes"][0],
        "new_password": "new-password-of-sufficient-length",
    }, headers={"Origin": origin})
    assert successful.status_code == 200
    assert successful.json() == {"ok": True}


def test_recovery_frontend_avoids_interpolated_html():
    root = Path(__file__).resolve().parents[1] / "app/static"
    js = (root / "app.js").read_text()
    login_js = (root / "login.js").read_text()
    assert "innerHTML" not in js and "innerHTML" not in login_js
    assert "password-change-form" in (root / "index.html").read_text()
    assert "recovery-generate-form" in (root / "index.html").read_text()
    assert "recoveryForm" in (root / "login.html").read_text()
    assert "navigator.clipboard.writeText" in js
