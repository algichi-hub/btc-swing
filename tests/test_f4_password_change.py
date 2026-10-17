"""F4 password change: session authorization, password rotation and revocation."""
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import service as auth_module
from app.auth.http import (
    get_auth_service, get_current_session_and_user, verify_csrf_token,
)
from app.auth.security import verify_password


@pytest.fixture
def auth_service(monkeypatch, tmp_path):
    path = tmp_path / "auth.sqlite"
    from app.storage.database import SCHEMA
    with sqlite3.connect(path) as con:
        con.executescript(SCHEMA)

    def connect_sqlite(_path):
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    monkeypatch.setattr(auth_module, "connect", connect_sqlite)
    service = auth_module.AuthService(db_path=path)
    user = service.create_user("admin", "old-very-long-password-001")
    return service, user


def test_password_rotation_revokes_all_sessions(auth_service):
    service, user = auth_service
    _, token1 = service.create_session(user.id)
    _, token2 = service.create_session(user.id)
    assert service.validate_session(token1) is not None
    assert service.change_password(user.id, "wrong-password", "new-very-long-password-001") is False
    assert service.validate_session(token1) is not None
    assert service.change_password(user.id, "old-very-long-password-001", "new-very-long-password-001") is True
    assert service.validate_session(token1) is None
    assert service.validate_session(token2) is None
    assert service.authenticate("admin", "old-very-long-password-001") is None
    assert service.authenticate("admin", "new-very-long-password-001") is not None


def test_password_rotation_policy(auth_service):
    service, user = auth_service
    with pytest.raises(ValueError):
        service.change_password(user.id, "old-very-long-password-001", "too-short")
    with pytest.raises(ValueError):
        service.change_password(user.id, "old-very-long-password-001", "old-very-long-password-001")


def test_change_password_endpoint_fail_closed(monkeypatch, auth_service):
    from app.main import public_router
    from app.config import settings
    service, user = auth_service
    app = FastAPI()
    app.include_router(public_router)
    app.dependency_overrides[get_auth_service] = lambda: service
    client = TestClient(app)
    data = {"current_password": "old-very-long-password-001",
            "new_password": "new-very-long-password-001"}
    route = "/api/auth/change-password"

    assert client.post(route, json=data).status_code == 403  # Origin required
    assert client.post(route, json=data, headers={"Origin": "https://foreign.invalid"}).status_code == 403
    allowed = settings.auth_allowed_origins[0] if settings.auth_allowed_origins else "https://localhost"
    assert client.post(route, json=data, headers={"Origin": allowed}).status_code == 401

    # A fake authorized session does not bypass CSRF; the token is still required.
    _, raw_token = service.create_session(user.id)
    session_user = service.validate_session(raw_token)
    app.dependency_overrides[get_current_session_and_user] = lambda: session_user
    assert client.post(route, json=data, headers={"Origin": allowed}).status_code == 403
    app.dependency_overrides[verify_csrf_token] = lambda: None
    denied = client.post(route, json={"current_password": "wrong",
                                     "new_password": data["new_password"]},
                         headers={"Origin": allowed})
    assert denied.status_code == 400
    assert service.authenticate("admin", data["current_password"]) is not None
    success = client.post(route, json=data, headers={"Origin": allowed})
    assert success.status_code == 200
    assert success.json() == {"ok": True}
    assert "btc_session=" in success.headers.get("set-cookie", "")
    assert service.authenticate("admin", data["new_password"]) is not None
