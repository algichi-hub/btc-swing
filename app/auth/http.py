import hmac
import json
from typing import Any

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from app.auth.models import AuthSession, User, UserRole
from app.auth.security import derive_csrf_token, normalize_username
from app.auth.service import AuthService
from app.config import settings

AUTH_COOKIE_NAME = "btc_session"
MAX_LOGIN_BODY_BYTES = 16384  # 16 KiB


def get_auth_service(request: Request) -> AuthService:
    """Provides AuthService instance, allowing test dependency overrides or app.state injection."""
    app_service = getattr(request.app.state, "auth_service", None)
    if app_service is not None:
        return app_service
    return AuthService(db_path=settings.database_path)


def set_session_cookie(response: Response, raw_token: str) -> None:
    """Attaches canonical btc_session cookie to the response."""
    max_age = settings.auth_session_ttl_hours * 3600
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def delete_session_cookie(response: Response) -> None:
    """Explicitly deletes the canonical btc_session cookie."""
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        samesite="strict",
        secure=settings.auth_cookie_secure,
        httponly=True,
    )


def verify_csrf_origin(request: Request) -> None:
    """Fail-closed CSRF origin defense for state-mutating requests.

    In Block 3, Origin header is MANDATORY for all POST, PUT, PATCH, DELETE requests
    and must match AUTH_ALLOWED_ORIGINS exactly. Missing Origin or foreign Origin returns 403.
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if not origin or not origin.strip():
            raise HTTPException(status_code=403, detail="Origin ausente no permitido")

        clean_origin = origin.strip().rstrip("/")
        allowed = [o.rstrip("/") for o in settings.auth_allowed_origins]
        if clean_origin not in allowed:
            raise HTTPException(status_code=403, detail="Origin no autorizado")


def get_current_session_and_user(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> tuple[AuthSession, User]:
    """Extracts and validates session from btc_session cookie, returning both session and user."""
    raw_token = request.cookies.get(AUTH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="No autenticado")

    result = auth_service.validate_session(raw_token)
    if result is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    session, user = result
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="No autenticado")

    return session, user


def get_current_user(
    session_user: tuple[AuthSession, User] = Depends(get_current_session_and_user),
) -> User:
    """Extracts authenticated user from validated session."""
    _, user = session_user
    return user


def verify_csrf_token(
    request: Request,
    session_user: tuple[AuthSession, User] = Depends(get_current_session_and_user),
) -> None:
    """Validates X-CSRF-Token header against HMAC derived from current session."""
    session, _ = session_user
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_header or not csrf_header.strip():
        raise HTTPException(status_code=403, detail="Token CSRF ausente")

    expected_csrf = derive_csrf_token(session.session_token_hash, settings.auth_csrf_secret)
    if not hmac.compare_digest(csrf_header.strip().lower(), expected_csrf):
        raise HTTPException(status_code=403, detail="Token CSRF inválido")


def require_authenticated(user: User = Depends(get_current_user)) -> User:
    """Requires an authenticated user with active session (VIEWER or ADMIN)."""
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Requires an authenticated user with ADMIN role."""
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return user


async def read_bounded_request_body(request: Request, max_bytes: int = MAX_LOGIN_BODY_BYTES) -> bytes:
    """Reads request body up to max_bytes, rejecting oversized requests with 413.

    Protects against both oversized Content-Length headers and unbounded chunked/streaming requests.
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
            if cl > max_bytes:
                raise HTTPException(status_code=413, detail="Cuerpo de petición excede el límite de 16 KiB")
        except ValueError:
            raise HTTPException(status_code=400, detail="Content-Length inválido")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise HTTPException(status_code=413, detail="Cuerpo de petición excede el límite de 16 KiB")

    return bytes(body)


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str
    password: str
