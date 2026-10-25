"""P2 Railway build configuration safety checks."""
from pathlib import Path


def test_railway_installs_pinned_pool_dependency():
    requirements = Path("requirements-f5.txt").read_text(encoding="utf-8")
    dockerfile = Path("deploy/railway-api.Dockerfile").read_text(encoding="utf-8")
    assert "psycopg-pool==3.2.8" in requirements
    assert "psycopg-pool==3.2.12" not in requirements
    assert "requirements-f5.txt" in dockerfile
    assert "pip install --no-cache-dir -r requirements-f5.txt" in dockerfile
    assert "import psycopg_pool" in dockerfile


def test_api_only_pool_not_used_by_engine():
    src = Path("app/storage/postgres.py").read_text(encoding="utf-8")
    assert 'os.getenv("BTC_PROCESS_ROLE") == "api"' in src
    assert "min_size=0, max_size=2" in src
    assert "return PgConnection(psycopg.connect(" in src


def test_pool_closed_at_api_shutdown():
    src = Path("app/main.py").read_text(encoding="utf-8")
    assert "finally:" in src
    assert "close_api_pool()" in src
