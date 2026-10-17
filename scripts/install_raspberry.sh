#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[btc_swing_trade] Raspberry install bootstrap"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3.11+ first." >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
print(f"Using Python {sys.version.split()[0]}")
PY

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
else
  echo "Reusing existing .venv"
fi

. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data

if [[ ! -f .env ]]; then
  echo "Missing .env. Create it first: cp .env.example .env" >&2
  echo "Then edit secrets and runtime values before starting the service." >&2
  exit 1
fi

python - <<'PY'
from app.config import settings
from app.settings.service import SettingsService
from app.storage.database import initialize

initialize(settings.database_path)
settings_service = SettingsService(
    database_path=settings.database_path,
    daily_default=settings.daily_swing_candles_default,
    backtest_default=settings.backtest_candles_default,
)
settings_service.apply_defaults()
print(f"Database ready at {settings.database_path}")
PY

python - <<'PY'
from app.main import automation_status, health

health_payload = health()
automation_payload = automation_status()
if health_payload.get("status") != "ok":
    raise SystemExit("Health smoke check failed")

print("Health smoke check: ok")
print(f"Automation interval_seconds: {automation_payload.get('interval_seconds')}")
print(f"Automation timezone: {automation_payload.get('timezone')}")
PY

cat <<'EOF'

Next steps (systemd):
1. Edit deploy/btc-swing-trade.service and set User/Group/WorkingDirectory if needed.
2. Copy service file:
   sudo cp deploy/btc-swing-trade.service /etc/systemd/system/btc-swing-trade.service
3. Reload and enable:
   sudo systemctl daemon-reload
   sudo systemctl enable btc-swing-trade
   sudo systemctl start btc-swing-trade
4. Verify:
   sudo systemctl status btc-swing-trade
   sudo journalctl -u btc-swing-trade -f

EOF
