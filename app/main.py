from __future__ import annotations

from contextlib import asynccontextmanager
import os
from datetime import datetime, timedelta, timezone
import hmac
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import (
    AUTH_COOKIE_NAME,
    AuthService,
    AuthSession,
    LoginPayload,
    User,
    delete_session_cookie,
    get_auth_service,
    get_current_session_and_user,
    get_current_user,
    normalize_username,
    read_bounded_request_body,
    require_admin,
    require_authenticated,
    set_session_cookie,
    verify_csrf_origin,
    verify_csrf_token,
)

from app.api.operations import router as operations_router
from app.automation.scheduler import AutomationScheduler
from app.automation.trading_engine import (
    RUNTIME_LAST_CYCLE_ERROR_KEY,
    RUNTIME_LAST_CYCLE_SUCCESS_KEY,
    RUNTIME_LAST_MARKET_CYCLE_AT_KEY,
    RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY,
    RUNTIME_TRADE_WINDOW_OPEN_KEY,
    TradingAutomationEngine,
)
from app.config import PROJECT_ROOT, settings
from app.indicators.stoch_rsi import stochastic_rsi
from app.indicators.volume import relative_volume
from app.market.hyperliquid import HyperliquidClient, closed_candles
from app.notifications.telegram import TelegramDeliveryError, TelegramNotifier
from app.settings.service import (
    BACKTEST_CANDLES,
    CLUSTER_TOLERANCE_PCT,
    DAILY_SWING_CANDLES,
    LOOKBACK_DAYS,
    MIN_CONFIRMATIONS,
    MIN_OPERATIONAL_RANGE_PCT,
    OPERATIONAL_RANGE_PCT,
    PIVOT_LEFT,
    PIVOT_RIGHT,
    PNL_CHART_DAYS,
    SMA20_FILTER_PCT,
    VOLUME_BASELINE_PERIOD,
    VOLUME_CONFIRMATION_THRESHOLD,
    SettingsService,
    SettingsValidationError,
)
from app.storage.database import initialize
from app.storage.trade_repository import TradeRepository, build_setup_timeline_response
from app.strategy.dashboard import build_dashboard_state
from app.strategy.setup_context import SetupContext, SetupContextManager
from app.strategy.swing_range import split_daily_candles_for_swing


class SettingsUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    daily_swing_candles: int | None = None
    backtest_candles: int | None = None
    lookback_days: int | None = None
    pivot_left: int | None = None
    pivot_right: int | None = None
    min_confirmations: int | None = None
    cluster_tolerance_pct: float | None = None
    sma20_filter_pct: float | None = None
    operational_range_pct: float | None = None
    min_operational_range_pct: float | None = None
    pnl_chart_days: int | None = None
    volume_baseline_period: int | None = None
    volume_confirmation_threshold: float | None = None
    pnl_recap_weekday: str | None = None
    pnl_recap_time: str | None = None

    @model_validator(mode="before")
    @classmethod
    def check_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data:
                raise ValueError("No settings were provided")
            for key, value in data.items():
                if value is None:
                    raise ValueError(f"{key} must not be null")
        return data


settings_service = SettingsService(
    database_path=settings.database_path,
    daily_default=settings.daily_swing_candles_default,
    backtest_default=settings.backtest_candles_default,
)
trade_repository = TradeRepository(settings.database_path)
telegram_notifier = TelegramNotifier(
    token=settings.telegram_bot_token,
    chat_id=settings.telegram_chat_id,
)
setup_context_manager = SetupContextManager(repository=trade_repository)


def recover_downtime_opportunity(
    repository: TradeRepository,
    manager: SetupContextManager,
    settings: Any,
    client_factory: Any | None = None,
) -> None:
    active_opp = repository.get_active_opportunity(settings.coin)
    if active_opp is None:
        return

    setup_id = str(active_opp["setup_id"])
    side = str(active_opp["side"])
    support = float(active_opp["support"])
    resistance = float(active_opp["resistance"])

    # Determine recovery start: prefer latest engine snapshot for this setup, fallback to opportunity created_at
    latest_snapshot = repository.get_latest_snapshot_for_setup(setup_id)
    if latest_snapshot is not None and latest_snapshot.get("created_at"):
        recovery_start_iso = str(latest_snapshot["created_at"])
    else:
        recovery_start_iso = str(active_opp["created_at"])

    try:
        recovery_start_dt = datetime.fromisoformat(recovery_start_iso)
        if recovery_start_dt.tzinfo is None:
            recovery_start_dt = recovery_start_dt.replace(tzinfo=timezone.utc)
        recovery_start_ms = int(recovery_start_dt.timestamp() * 1000)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        elapsed_ms = max(0, now_ms - recovery_start_ms)
        candles_needed = max(int(elapsed_ms / (60 * 60 * 1000)) + 5, 2)

        factory = client_factory or (lambda: HyperliquidClient(settings.info_url))
        client = factory()
        hourly = closed_candles(client.get_candles(settings.coin, "1h", candles_needed))

        # Validate complete historical coverage
        is_coverage_complete = True
        if not hourly:
            is_coverage_complete = False
        elif hourly[0].open_time_ms > recovery_start_ms:
            # Oldest candle does not reach back to recovery_start_ms
            is_coverage_complete = False
        else:
            # Check for gaps between consecutive candles (> 1 hour + margin)
            for i in range(1, len(hourly)):
                if (hourly[i].open_time_ms - hourly[i - 1].open_time_ms) > (3600 * 1000 + 10000):
                    is_coverage_complete = False
                    break

        if not is_coverage_complete:
            repository.mark_opportunity_invalidated(
                setup_id,
                reason="DOWNTIME_COVERAGE_INCOMPLETE",
            )
            manager.clear()
            return

        downtime_candles = [c for c in hourly if c.close_time_ms >= recovery_start_ms]

        breached = False
        if side == "LONG":
            breached = any(c.low < support for c in downtime_candles)
        elif side == "SHORT":
            breached = any(c.high > resistance for c in downtime_candles)

        if breached:
            repository.mark_opportunity_invalidated(
                setup_id,
                reason="DOWNTIME_BOUNDARY_BREACH",
            )
            manager.clear()
            return
    except Exception:
        # Fail-closed if market data cannot be obtained
        repository.mark_opportunity_invalidated(
            setup_id,
            reason="DOWNTIME_COVERAGE_INCOMPLETE",
        )
        manager.clear()
        return

    setup_ctx = SetupContext.from_opportunity(active_opp)
    manager.restore_setup(setup_ctx)


def build_dashboard_payload() -> dict:
    client = HyperliquidClient(settings.info_url)

    app_settings = settings_service.get_all()
    price = client.get_mid(settings.coin)

    lookback_days = int(app_settings.get(LOOKBACK_DAYS, app_settings.get(DAILY_SWING_CANDLES, 120)))
    backtest_count = int(app_settings[BACKTEST_CANDLES])
    pivot_left = int(app_settings.get(PIVOT_LEFT, settings.swing_left))
    pivot_right = int(app_settings.get(PIVOT_RIGHT, settings.swing_right))
    min_confirmations = int(app_settings.get(MIN_CONFIRMATIONS, 2))
    cluster_tolerance_pct = float(app_settings.get(CLUSTER_TOLERANCE_PCT, settings.swing_cluster_tolerance_pct * 100.0))
    sma20_filter_pct = float(app_settings.get(SMA20_FILTER_PCT, settings.swing_sma_max_distance_pct * 100.0))
    operational_range_pct = float(app_settings.get(OPERATIONAL_RANGE_PCT, 10.0))
    min_operational_range_pct = float(app_settings.get(MIN_OPERATIONAL_RANGE_PCT, 0.0))
    volume_baseline_period = int(app_settings.get(VOLUME_BASELINE_PERIOD, settings.volume_baseline_period))
    volume_confirmation_threshold = float(app_settings.get(VOLUME_CONFIRMATION_THRESHOLD, settings.volume_confirmation_threshold))

    hourly_count = max(140, min(settings.hourly_candles, 600))
    daily_required_closed = lookback_days + (settings.swing_sma_period - 1)
    daily_fetch_margin = 6

    daily_closed = closed_candles(
        client.get_candles(settings.coin, "1d", daily_required_closed + daily_fetch_margin)
    )
    daily_warmup, daily_analysis = split_daily_candles_for_swing(
        closed_candles=daily_closed,
        analysis_sessions=lookback_days,
        sma_period=settings.swing_sma_period,
        strict=True,
    )

    hourly = closed_candles(client.get_candles(settings.coin, "1h", hourly_count))

    return build_dashboard_state(
        price=price,
        daily_candles=daily_analysis,
        daily_warmup_candles=daily_warmup,
        hourly_candles=hourly,
        settings=settings,
        daily_candles_used=lookback_days,
        backtest_candles_used=backtest_count,
        refresh_interval_seconds=settings.refresh_interval_seconds,
        lookback_days=lookback_days,
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        min_confirmations=min_confirmations,
        cluster_tolerance_pct=cluster_tolerance_pct,
        sma20_filter_pct=sma20_filter_pct,
        operational_range_pct=operational_range_pct,
        min_operational_range_pct=min_operational_range_pct,
        volume_baseline_period=volume_baseline_period,
        volume_confirmation_threshold=volume_confirmation_threshold,
        setup_context_manager=setup_context_manager,
    )


automation_engine = TradingAutomationEngine(
    settings=settings,
    repository=trade_repository,
    telegram_notifier=telegram_notifier,
    dashboard_provider=build_dashboard_payload,
    settings_service=settings_service,
)
automation_scheduler = AutomationScheduler(
    engine=automation_engine,
    settings=settings,
    settings_service=settings_service,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_runtime()
    if os.environ.get('BTC_PROCESS_ROLE') == 'api':
        if os.environ.get('BTC_DB_BACKEND') != 'postgres':
            raise RuntimeError('Cloud API requires PostgreSQL')
        # Cloud API never launches market scheduler, replay, bootstrap, or DDL.
        yield
        return
    initialize(settings_service.database_path)
    settings_service.apply_defaults()
    recover_downtime_opportunity(
        repository=trade_repository,
        manager=setup_context_manager,
        settings=settings,
    )
    automation_engine.bootstrap()
    automation_scheduler.start()
    yield
    automation_scheduler.stop()


public_router = APIRouter()
viewer_router = APIRouter(prefix="/api", dependencies=[Depends(verify_csrf_origin), Depends(require_authenticated)])
admin_router = APIRouter(prefix="/api", dependencies=[Depends(verify_csrf_origin), Depends(require_admin), Depends(verify_csrf_token)])


@public_router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0", "env": settings.app_env, "coin": settings.coin}


@public_router.get("/login", include_in_schema=False, response_model=None)
def login_page(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    raw_token = request.cookies.get(AUTH_COOKIE_NAME)
    if raw_token:
        result = auth_service.validate_session(raw_token)
        if result is not None:
            return RedirectResponse(url="/", status_code=307)
    return FileResponse(PROJECT_ROOT / "app" / "static" / "login.html")


@public_router.post("/api/auth/login")
async def login(
    request: Request,
    response: Response,
    _origin: None = Depends(verify_csrf_origin),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    # 1. Read body acotado (16 KiB limit) BEFORE Pydantic parsing
    body_bytes = await read_bounded_request_body(request, max_bytes=16384)
    try:
        payload = LoginPayload.model_validate_json(body_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="JSON malformado o inválido") from exc

    try:
        clean_username = normalize_username(payload.username)
    except ValueError:
        clean_username = payload.username.strip().lower()[:64] or "invalid"

    client_ip = request.client.host if request.client else "127.0.0.1"

    # 2. Check rate limits (before Argon2 verification!)
    is_locked, retry_after, _ = auth_service.check_login_rate_limits(clean_username, client_ip)
    if is_locked:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de acceso fallidos. Por favor, inténtelo de nuevo más tarde.",
            headers={"Retry-After": str(max(1, retry_after))},
        )

    # 3. Authenticate user
    user = auth_service.authenticate(payload.username, payload.password)
    if user is None or not user.enabled:
        status, retry_after, _ = auth_service.record_login_failure(clean_username, client_ip)
        if status == "BLOCKED":
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos de acceso fallidos. Por favor, inténtelo de nuevo más tarde.",
                headers={"Retry-After": str(max(1, retry_after))},
            )
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    # 4. Check if any bucket became locked during Argon2 verification (race protection)
    is_locked_after, retry_after_post, _ = auth_service.check_login_rate_limits(clean_username, client_ip)
    if is_locked_after:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de acceso fallidos. Por favor, inténtelo de nuevo más tarde.",
            headers={"Retry-After": str(max(1, retry_after_post))},
        )

    # 5. Authentication succeeded: reset user rate limit bucket ONLY
    auth_service.reset_user_login_attempts(clean_username)

    # Opportunistic cleanup of stale attempts
    try:
        auth_service.prune_stale_login_attempts()
    except Exception:
        pass

    # 5. Session fixation mitigation: revoke previous session if present in cookie
    previous_token = request.cookies.get(AUTH_COOKIE_NAME)
    if previous_token:
        try:
            auth_service.revoke_session(previous_token)
        except Exception:
            pass

    # 6. Create new session and issue cookie
    session, raw_token = auth_service.create_session(user.id)
    set_session_cookie(response, raw_token)

    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        },
    }


@public_router.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    _origin: None = Depends(verify_csrf_origin),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    raw_token = request.cookies.get(AUTH_COOKIE_NAME)
    if not raw_token:
        delete_session_cookie(response)
        return {"ok": True, "message": "Sesión cerrada correctamente"}

    result = auth_service.validate_session(raw_token)
    if result is None:
        delete_session_cookie(response)
        return {"ok": True, "message": "Sesión cerrada correctamente"}

    # Valid session: MUST validate X-CSRF-Token!
    session, _ = result
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_header or not csrf_header.strip():
        raise HTTPException(status_code=403, detail="Token CSRF ausente")

    expected_csrf = auth_service.derive_csrf_token(session)
    if not hmac.compare_digest(csrf_header.strip().lower(), expected_csrf):
        raise HTTPException(status_code=403, detail="Token CSRF inválido")

    auth_service.revoke_session(raw_token)
    delete_session_cookie(response)
    return {"ok": True, "message": "Sesión cerrada correctamente"}


@viewer_router.get("/auth/csrf")
def get_csrf(
    response: Response,
    session_user: tuple[AuthSession, User] = Depends(get_current_session_and_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    session, _ = session_user
    token = auth_service.derive_csrf_token(session)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return {"csrf_token": token}


@viewer_router.get("/auth/me")
def get_me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }



@viewer_router.get("/market/snapshot")
def market_snapshot() -> dict:
    client = HyperliquidClient(settings.info_url)
    mid = client.get_mid(settings.coin)
    app_settings = settings_service.get_all()
    vol_period = int(app_settings.get(VOLUME_BASELINE_PERIOD, settings.volume_baseline_period))
    hourly = closed_candles(client.get_candles(settings.coin, "1h", max(100, vol_period + 10)))
    rvol = relative_volume(hourly, vol_period)
    srsi = stochastic_rsi([c.close for c in hourly], settings.rsi_period, settings.stoch_rsi_period, settings.stoch_k, settings.stoch_d)
    return {
        "coin": settings.coin,
        "price": mid,
        "volume_1h_relative": None if rvol is None else round(rvol, 3),
        "stoch_rsi_1h": None if srsi is None else {k: round(v, 2) for k, v in srsi.items()},
        "note": "Market snapshot. Strategy and backtest modules follow the product specification in AGENTS.md.",
    }


@viewer_router.get("/settings")
def get_app_settings() -> dict[str, Any]:
    return settings_service.get_all()


@admin_router.put("/settings")
def update_app_settings(payload: SettingsUpdatePayload) -> dict[str, Any]:
    try:
        updates = payload.model_dump(exclude_unset=True)
        recap_changed = "pnl_recap_weekday" in updates or "pnl_recap_time" in updates

        if recap_changed:
            previous_settings = settings_service.get_all()
            rollback_payload = {k: previous_settings[k] for k in updates if k in previous_settings}
            saved = settings_service.update_many(updates)
            try:
                automation_scheduler.reschedule_pnl_recap(
                    weekday=updates.get("pnl_recap_weekday"),
                    time_str=updates.get("pnl_recap_time"),
                )
            except Exception as exc:
                try:
                    settings_service.update_many(rollback_payload)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to reschedule recap trigger: {exc}",
                ) from exc
            return saved

        return settings_service.update_many(updates)
    except SettingsValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@viewer_router.get("/dashboard")
def dashboard() -> dict:
    return build_dashboard_payload()


@viewer_router.get("/history")
def history(limit: int = 100) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 500))
    items = trade_repository.list_trade_history(limit=safe_limit)

    for item in items:
        signal_id = int(item["id"])
        item["events"] = trade_repository.list_trade_events(signal_id)

    return {
        "items": items,
        "limit": safe_limit,
    }


@admin_router.post("/database/reset")
def reset_database() -> dict[str, Any]:
    try:
        trade_repository.reset_operational_data()
        setup_context_manager.clear()
        trade_repository.set_runtime_bool(RUNTIME_TRADE_WINDOW_OPEN_KEY, False)
        trade_repository.set_runtime_state(
            RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY,
            datetime.now(timezone.utc).isoformat(),
        )
        return {"ok": True, "message": "Base de datos reseteada correctamente."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database reset failed: {exc}") from exc


@viewer_router.get("/pnl/daily-cumulative")
def pnl_chart(days: int | None = Query(default=None, ge=1)) -> dict[str, Any]:
    app_settings = settings_service.get_all()
    chart_days = days if isinstance(days, int) else int(app_settings.get(PNL_CHART_DAYS, 30))
    points = trade_repository.get_daily_cumulative_pnl(days=chart_days)
    return {
        "points": points,
        "days": chart_days,
        "total_points": len(points),
        "total_realized_pnl": points[-1]["cumulative_pnl"] if points else 0.0,
    }


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@viewer_router.get("/engine-snapshots")
def get_engine_snapshots(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    setup_id: str | None = None,
    signal_state: str | None = None,
    signal_side: str | None = None,
    block_reason: str | None = None,
    trade_window_open: bool | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> dict[str, Any]:
    if from_ts is not None and _parse_iso_timestamp(from_ts) is None:
        raise HTTPException(status_code=422, detail="Invalid from_ts timestamp format")
    if to_ts is not None and _parse_iso_timestamp(to_ts) is None:
        raise HTTPException(status_code=422, detail="Invalid to_ts timestamp format")

    return trade_repository.list_engine_snapshots(
        limit=limit,
        offset=offset,
        setup_id=setup_id,
        signal_state=signal_state,
        signal_side=signal_side,
        block_reason=block_reason,
        trade_window_open=trade_window_open,
        from_ts=from_ts,
        to_ts=to_ts,
    )


@viewer_router.get("/engine-snapshots/{snapshot_id}")
def get_engine_snapshot(snapshot_id: int) -> dict[str, Any]:
    snapshot = trade_repository.get_engine_snapshot_by_id(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Engine snapshot not found")
    return snapshot


@viewer_router.get("/setup-history/{setup_id}")
def get_setup_history(setup_id: str) -> dict[str, Any]:
    snapshots = trade_repository.list_engine_snapshots_for_setup(setup_id)
    if not snapshots:
        raise HTTPException(status_code=404, detail="Setup history not found")
    return build_setup_timeline_response(setup_id, snapshots)


@viewer_router.get("/automation/status")
def automation_status() -> dict[str, bool | int | str | None]:
    scheduler_status = automation_scheduler.market_cycle_status()

    last_market_cycle_at = trade_repository.get_runtime_state(RUNTIME_LAST_MARKET_CYCLE_AT_KEY)
    last_cycle_success = trade_repository.get_runtime_bool(RUNTIME_LAST_CYCLE_SUCCESS_KEY)
    last_cycle_error = trade_repository.get_runtime_state(RUNTIME_LAST_CYCLE_ERROR_KEY) or None

    stale = False
    parsed_last_cycle = _parse_iso_timestamp(last_market_cycle_at)
    if parsed_last_cycle is None:
        last_market_cycle_at = None
    else:
        stale = (datetime.now(timezone.utc) - parsed_last_cycle) > timedelta(minutes=10)

    get_schedule = getattr(automation_scheduler, "get_recap_schedule", None)
    if get_schedule is not None:
        recap_weekday, recap_hour, recap_minute = get_schedule()
    else:
        recap_weekday, recap_hour, recap_minute = "SUNDAY", 5, 0

    return {
        "running": bool(scheduler_status["running"]),
        "interval_seconds": int(scheduler_status["interval_seconds"]),
        "last_market_cycle_at": last_market_cycle_at,
        "next_market_cycle_at": scheduler_status["next_market_cycle_at"],
        "last_cycle_success": last_cycle_success,
        "last_cycle_error": last_cycle_error,
        "daily_summary_time": f"{settings.telegram_daily_report_hour:02d}:{settings.telegram_daily_report_minute:02d}",
        "pnl_recap_weekday": recap_weekday,
        "pnl_recap_time": f"{recap_hour:02d}:{recap_minute:02d}",
        "timezone": settings.telegram_timezone,
        "is_stale": stale,
    }


@viewer_router.get("/telegram/status")
def telegram_status() -> dict[str, str | bool | None]:
    last_recap = (
        trade_repository.last_successful_telegram_event_at("PNL_RECAP")
        or trade_repository.last_successful_telegram_event_at("DAILY_SUMMARY")
    )
    return {
        "enabled": bool(settings.telegram_enabled),
        "configured": bool(telegram_notifier.configured),
        "last_test_at": trade_repository.last_successful_telegram_event_at("TEST"),
        "last_trade_alert_at": trade_repository.last_successful_telegram_event_at("TRADE_ALERT"),
        "last_daily_summary_at": last_recap,
        "last_pnl_recap_at": last_recap,
    }


@admin_router.post("/telegram/test")
def telegram_test() -> dict[str, bool]:
    if not settings.telegram_enabled:
        raise HTTPException(status_code=400, detail="Telegram is disabled")
    if not telegram_notifier.configured:
        raise HTTPException(status_code=400, detail="Telegram is not fully configured")

    message = "\u2705 BTC Swing Trade: Telegram configurado correctamente."
    event_key = f"TEST:{datetime.now(timezone.utc).isoformat()}"

    try:
        message_id = telegram_notifier.send_message(message)
        trade_repository.record_telegram_event(
            event_type="TEST",
            event_key=event_key,
            success=True,
            telegram_message_id=message_id,
        )
    except TelegramDeliveryError as exc:
        trade_repository.record_telegram_event(
            event_type="TEST",
            event_key=event_key,
            success=False,
            error_message=exc.__class__.__name__,
        )
        raise HTTPException(status_code=502, detail="Telegram test message failed") from exc

    return {"ok": True}


def create_app(app_env: str | None = None) -> FastAPI:
    env = (app_env or settings.app_env).strip().lower()
    is_prod = env == "production"
    application = FastAPI(
        title="BTC Swing Trading Engine",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # 1. TrustedHostMiddleware
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.auth_allowed_hosts),
    )

    # 2. Security Headers, HSTS, and Cache-Control Middleware
    @application.middleware("http")
    async def security_headers_and_cache_middleware(request: Request, call_next):
        current_is_prod = is_prod or settings.app_env.strip().lower() == "production"
        try:
            response = await call_next(request)
        except Exception:
            if current_is_prod:
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Error interno del servidor"},
                )
            else:
                raise

        # Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )

        # HSTS only in production over genuine HTTPS (scope scheme only; no direct trust in X-Forwarded-* in Block 3)
        if current_is_prod and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"

        # Cache-Control policy
        path = request.url.path
        if path.startswith("/api/") or path == "/login" or path == "/":
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif path.startswith("/static/"):
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "public, max-age=3600"

        return response

    # 3. Production Generic 500 Exception Handler
    if is_prod:
        @application.exception_handler(Exception)
        async def production_exception_handler(request: Request, exc: Exception):
            if isinstance(exc, HTTPException):
                return await http_exception_handler(request, exc)
            if isinstance(exc, RequestValidationError):
                return await request_validation_exception_handler(request, exc)
            return JSONResponse(
                status_code=500,
                content={"detail": "Error interno del servidor"},
            )

    application.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")

    @application.get("/", include_in_schema=False, response_model=None)
    def index(
        request: Request,
        auth_service: AuthService = Depends(get_auth_service),
    ) -> Response:
        raw_token = request.cookies.get(AUTH_COOKIE_NAME)
        if not raw_token:
            return RedirectResponse(url="/login", status_code=307)
        result = auth_service.validate_session(raw_token)
        if result is None:
            return RedirectResponse(url="/login", status_code=307)
        return FileResponse(PROJECT_ROOT / "app" / "static" / "index.html")

    application.include_router(operations_router)
    application.include_router(public_router)
    application.include_router(viewer_router)
    application.include_router(admin_router)
    return application


app = create_app()
