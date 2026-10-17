"""F4 API integration with disposable PostgreSQL, including access control."""
import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module", autouse=True)
def disposable_db():
    if os.environ.get("BTC_TEST_DATABASE") != "YES" or os.environ.get("BTC_DB_BACKEND") != "postgres":
        pytest.skip("Requires disposable PostgreSQL instance")
    from app.storage.postgres import initialize_pg
    from app.storage.worker_migration import apply_worker_migration
    initialize_pg()
    apply_worker_migration()


@pytest.fixture
def client():
    from fastapi import FastAPI
    from app.api.operations import router
    from app.auth.http import require_authenticated
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield app, client, require_authenticated


def test_no_cookie_cannot_read_neon_logs(client):
    _, c, _ = client
    assert c.get("/api/ops/logs").status_code == 401
    assert c.get("/api/ops/status").status_code == 401


def test_read_only_authenticated_status_is_neon_backed(client):
    app,c,require_authenticated=client
    app.dependency_overrides[require_authenticated] = lambda: object()
    resp=c.get("/api/ops/status")
    assert resp.status_code == 200
    state=resp.json()
    assert state["source"]=="neon"
    assert state["worker"]["status"] in ("OK","ERROR","RETRASADO","SIN DATOS")


def test_filter_and_sensitive_log_redaction_on_real_postgres(client):
    from app.storage.postgres import connect_pg
    with connect_pg() as db:
        db.execute(
            "INSERT INTO operational_logs(service,severity,code,message) VALUES(%s,%s,%s,%s)",
            ("api","WARN","F4_AUDIT","password=example-secret")
        )
    app,c,require_authenticated=client
    app.dependency_overrides[require_authenticated] = lambda: object()
    resp=c.get("/api/ops/logs?severity=WARN&service=api&page=1&page_size=20")
    assert resp.status_code == 200
    data=resp.json()
    assert data["total"] >= 1
    entry=next(x for x in data["items"] if x["code"]=="F4_AUDIT")
    assert entry["message"]=="[REDACTED]"
    assert "example-secret" not in str(data)


def test_invalid_filter_rejected_before_postgres_query(client):
    app,c,require_authenticated=client
    app.dependency_overrides[require_authenticated] = lambda: object()
    response=c.get("/api/ops/logs?service=%27%3BDROP%20TABLE%20users")
    assert response.status_code==422


def test_static_frontend_no_dynamic_html_injection():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    js=(root/"app/static/ops.js").read_text()
    app_js=(root/"app/static/app.js").read_text()
    assert "innerHTML" not in js
    assert "innerHTML" not in app_js
    assert ".textContent" in js
    assert "URLSearchParams" in js


def test_vercel_proxy_only_routes_api_to_railway():
    import json
    from pathlib import Path
    config=json.loads((Path(__file__).resolve().parents[1]/"app/static/vercel.json").read_text())
    routes=config["rewrites"]
    proxy=[r for r in routes if r["source"]=="/api/:path*"]
    assert len(proxy)==1
    assert proxy[0]["destination"].startswith("https://btc-v5-api-preview-preview.up.railway.app/api/")
    assert not any("DATABASE_URL" in str(r) or "SECRET" in str(r) for r in config["rewrites"])


def test_f4_admin_bootstrap_does_not_require_ddl():
    from pathlib import Path
    src=(Path(__file__).resolve().parents[1]/"app/storage/bootstrap.py").read_text()
    assert "initialize_pg()" not in src
    from app.storage.postgres import connect_pg
    with connect_pg() as db:
        row=db.execute("""
          SELECT has_table_privilege('btc_v5_web_app','users','INSERT') AS can_create_user,
                 has_schema_privilege('btc_v5_web_app','public','CREATE') AS can_change_schema
        """).fetchone()
    assert row["can_create_user"] is True
    assert row["can_change_schema"] is False
