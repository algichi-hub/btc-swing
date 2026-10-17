$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path ".venv\Scripts\python.exe")) { throw "Missing .venv. Run scripts/setup_windows.ps1 first." }
$appHost = & .\.venv\Scripts\python.exe -c "from app.config import settings; print(settings.app_host)"
$appPort = & .\.venv\Scripts\python.exe -c "from app.config import settings; print(settings.app_port)"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host $appHost --port $appPort --reload
