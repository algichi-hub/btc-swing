from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.automation.trading_engine import (
    RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY,
    TradingAutomationEngine,
)
from app.config import Settings
from app.settings.service import (
    PNL_RECAP_TIME,
    PNL_RECAP_WEEKDAY,
    SettingsService,
)

MARKET_CYCLE_JOB_ID = "market-cycle"
PNL_RECAP_JOB_ID = "pnl-recap"
DAILY_SUMMARY_JOB_ID = PNL_RECAP_JOB_ID
MARKET_CYCLE_INTERVAL_SECONDS = 300


class AutomationScheduler:
    def __init__(
        self,
        *,
        engine: TradingAutomationEngine,
        settings: Settings,
        settings_service: SettingsService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.settings_service = settings_service
        self.logger = logger or logging.getLogger(__name__)
        self.scheduler = BackgroundScheduler(timezone=ZoneInfo(settings.telegram_timezone))
        self._started = False

    @property
    def market_cycle_interval_seconds(self) -> int:
        return MARKET_CYCLE_INTERVAL_SECONDS

    def market_cycle_status(self) -> dict[str, bool | int | str | None]:
        market_job = self.scheduler.get_job(MARKET_CYCLE_JOB_ID)
        next_market_cycle_at = None
        if market_job is not None and market_job.next_run_time is not None:
            next_market_cycle_at = market_job.next_run_time.isoformat()

        return {
            "running": bool(self._started and self.scheduler.running),
            "interval_seconds": self.market_cycle_interval_seconds,
            "next_market_cycle_at": next_market_cycle_at,
        }

    def get_recap_schedule(self) -> tuple[str, int, int]:
        weekday = "SUNDAY"
        hour = 5
        minute = 0
        if self.settings_service is not None:
            try:
                all_s = self.settings_service.get_all()
                weekday = str(all_s.get(PNL_RECAP_WEEKDAY, "SUNDAY")).upper()
                time_str = str(all_s.get(PNL_RECAP_TIME, "05:00"))
                parts = time_str.split(":")
                hour = int(parts[0])
                minute = int(parts[1])
            except Exception:
                pass
        return weekday, hour, minute

    def reschedule_pnl_recap(self, weekday: str | None = None, time_str: str | None = None) -> None:
        target_fn = getattr(self.engine, "run_pnl_recap", None)
        if target_fn is None:
            return

        current_weekday, current_hour, current_minute = self.get_recap_schedule()
        if weekday is not None:
            current_weekday = weekday.upper()
        if time_str is not None:
            parts = time_str.split(":")
            current_hour = int(parts[0])
            current_minute = int(parts[1])

        trigger = CronTrigger(
            day_of_week=current_weekday[:3].lower(),
            hour=current_hour,
            minute=current_minute,
            timezone=ZoneInfo(self.settings.telegram_timezone),
        )

        previous_job = self.scheduler.get_job(PNL_RECAP_JOB_ID)
        prev_state = None
        if previous_job is not None:
            prev_state = {
                "func": previous_job.func,
                "trigger": previous_job.trigger,
                "args": previous_job.args,
                "kwargs": previous_job.kwargs,
                "name": previous_job.name,
                "misfire_grace_time": previous_job.misfire_grace_time,
                "coalesce": previous_job.coalesce,
                "max_instances": previous_job.max_instances,
            }

        self.scheduler.add_job(
            target_fn,
            trigger=trigger,
            id=PNL_RECAP_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=180,
        )

        try:
            repo = getattr(self.engine, "repository", None)
            if repo is not None and hasattr(repo, "set_runtime_state"):
                repo.set_runtime_state(
                    RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY,
                    datetime.now(timezone.utc).isoformat(),
                )
        except Exception:
            if prev_state is not None:
                self.scheduler.add_job(
                    prev_state["func"],
                    trigger=prev_state["trigger"],
                    args=prev_state["args"],
                    kwargs=prev_state["kwargs"],
                    id=PNL_RECAP_JOB_ID,
                    name=prev_state["name"],
                    misfire_grace_time=prev_state["misfire_grace_time"],
                    coalesce=prev_state["coalesce"],
                    max_instances=prev_state["max_instances"],
                    replace_existing=True,
                )
            else:
                if self.scheduler.get_job(PNL_RECAP_JOB_ID) is not None:
                    self.scheduler.remove_job(PNL_RECAP_JOB_ID)
            raise

        self.logger.info(
            "PnL recap rescheduled: %s at %02d:%02d (%s)",
            current_weekday,
            current_hour,
            current_minute,
            self.settings.telegram_timezone,
        )

    def start(self) -> None:
        if self._started:
            return

        self.scheduler.add_job(
            self.engine.run_market_cycle,
            trigger="interval",
            seconds=self.market_cycle_interval_seconds,
            id=MARKET_CYCLE_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=90,
        )

        target_fn = getattr(self.engine, "run_pnl_recap", None)
        if target_fn is not None:
            weekday, hour, minute = self.get_recap_schedule()
            self.scheduler.add_job(
                target_fn,
                trigger=CronTrigger(
                    day_of_week=weekday[:3].lower(),
                    hour=hour,
                    minute=minute,
                    timezone=ZoneInfo(self.settings.telegram_timezone),
                ),
                id=PNL_RECAP_JOB_ID,
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=180,
            )

        self.scheduler.start()
        self._started = True
        self.logger.info("Automation scheduler started")

        recovery_fn = getattr(self.engine, "ensure_pending_pnl_recap", getattr(self.engine, "recover_missed_pnl_recap", None))
        if recovery_fn is not None:
            try:
                recovery_fn()
            except Exception:
                self.logger.exception("Initial pending PnL recap recovery failed")

    def stop(self) -> None:
        if not self._started:
            return

        self.scheduler.shutdown(wait=False)
        self._started = False
        self.logger.info("Automation scheduler stopped")
