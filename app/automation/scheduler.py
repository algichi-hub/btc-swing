from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.automation.trading_engine import TradingAutomationEngine
from app.config import Settings
from app.settings.service import SettingsService

MARKET_CYCLE_JOB_ID = "market-cycle"
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

        self.scheduler.start()
        self._started = True
        self.logger.info("Automation scheduler started")

    def stop(self) -> None:
        if not self._started:
            return

        self.scheduler.shutdown(wait=False)
        self._started = False
        self.logger.info("Automation scheduler stopped")
