"""Read-only, authenticated F4 operations log API.

Only server-generated operational telemetry is exposed, and never raw provider
errors, secrets or SQL diagnostics. Queries run against Postgres Preview/Prod.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.http import require_authenticated
from app.automation.cloud_worker import get_worker_health
from app.storage.postgres import connect_pg

router = APIRouter(prefix="/api/ops", tags=["operations"], dependencies=[Depends(require_authenticated)])

_ALLOWED_SERVICES = frozenset({"btc-v5-engine", "engine", "api", "push", "scheduler"})
_ALLOWED_SEVERITIES = frozenset({"INFO", "WARN", "ERROR"})
_SAFE_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_SENSITIVE = re.compile(r"(?i)(?:postgres(?:ql)?://|https?://|(?:token|password|secret|api[_-]?key)\s*[=:]|bearer\s+)")
_WORKER_KEY = "btc-v5-engine"


def _sanitize_code(value: object) -> str:
    code = str(value or "")
    return code if _SAFE_CODE.fullmatch(code) else "REDACTED"


def _sanitize_message(value: object) -> str:
    msg = str(value or "")
    if _SENSITIVE.search(msg):
        return "[REDACTED]"
    return re.sub(r"[\r\n\x00-\x1f]", " ", msg)[:240]


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


@router.get("/status")
def operations_status():
    health = get_worker_health(max_age_seconds=660)
    with connect_pg() as db:
        row = db.execute(
            "SELECT status,cycle_key,started_at,completed_at,error_code "
            "FROM worker_cycles ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        counts = db.execute(
            "SELECT count(*) AS errors_24h FROM operational_logs "
            "WHERE severity='ERROR' AND created_at>=now()-interval '24 hours'"
        ).fetchone()
    return {
        "worker": health,
        "last_cycle": ({
            "status": row["status"], "cycle_key": row["cycle_key"],
            "started_at": _iso(row["started_at"]),
            "completed_at": _iso(row["completed_at"]),
            "error_code": _sanitize_code(row["error_code"]) if row["error_code"] else None,
        } if row else None),
        "errors_24h": int(counts["errors_24h"]),
        "source": "neon",
    }


@router.get("/logs")
def operations_logs(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=25, ge=1, le=100),
    severity: str | None = Query(default=None),
    service: str | None = Query(default=None),
):
    if severity is not None and severity not in _ALLOWED_SEVERITIES:
        raise HTTPException(status_code=422, detail="Invalid severity filter")
    if service is not None and service not in _ALLOWED_SERVICES:
        raise HTTPException(status_code=422, detail="Invalid service filter")
    filters, params = [], []
    if severity:
        filters.append("severity=%s"); params.append(severity)
    if service:
        filters.append("service=%s"); params.append(service)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    with connect_pg() as db:
        total = db.execute(
            "SELECT count(*) AS total FROM operational_logs" + where, tuple(params)
        ).fetchone()
        rows = db.execute(
            "SELECT id,created_at,service,severity,cycle_key,code,message "
            "FROM operational_logs" + where + " ORDER BY id DESC LIMIT %s OFFSET %s",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "page": page, "page_size": page_size, "total": int(total["total"]),
        "items": [
            {"id": int(r["id"]), "created_at": _iso(r["created_at"]),
             "service": r["service"] if r["service"] in _ALLOWED_SERVICES else "other",
             "severity": r["severity"], "cycle_key": r["cycle_key"],
             "code": _sanitize_code(r["code"]), "message": _sanitize_message(r["message"])}
            for r in rows
        ],
    }
