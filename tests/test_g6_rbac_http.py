"""HTTP authorization regression with simulated sessions; does not mutate any database."""
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth.http import get_auth_service
from app.auth.models import AuthSession, User

class Sessions:
    def validate_session(self, token):
        if token not in {"admin-test", "viewer-test"}:
            return None
        role = "ADMIN" if token == "admin-test" else "VIEWER"
        user = User(id=1, username=role.lower(), password_hash="unused", role=role,
                    enabled=True, created_at="2026-01-01",updated_at="2026-01-01")
        session = AuthSession(id=1,session_token_hash="testhash",user_id=1,
                              created_at="2026-01-01",expires_at="2099-01-01",
                              last_seen_at="2026-01-01")
        return session,user

def client():
    app=create_app()
    app.dependency_overrides[get_auth_service]=lambda: Sessions()
    return TestClient(app,follow_redirects=False)

def test_anonymous_denied_admin_routes():
    with client() as c:
        assert c.get("/api/auth/me").status_code == 401
        assert c.put("/api/settings",json={},headers={"origin":"http://testserver"}).status_code == 401

def test_viewer_can_identify_self_but_cannot_write_settings_or_reset():
    with client() as c:
        c.cookies.set("btc_session","viewer-test")
        assert c.get("/api/auth/me").json()["role"] == "VIEWER"
        assert c.put("/api/settings",json={},headers={"origin":"http://testserver"}).status_code == 403
        assert c.post("/api/database/reset",headers={"origin":"http://testserver"}).status_code == 403

def test_admin_valid_session_but_cannot_write_without_origin_or_csrf():
    with client() as c:
        c.cookies.set("btc_session","admin-test")
        assert c.get("/api/auth/me").json()["role"] == "ADMIN"
        assert c.put("/api/settings",json={}).status_code == 403
        assert c.put("/api/settings",json={},headers={"origin":"http://testserver"}).status_code == 403
