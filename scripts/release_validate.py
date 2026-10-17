from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_BUILD_DIR = REPO_ROOT / "release_build"
STAGING_DIR = RELEASE_BUILD_DIR / "staging_clean_install"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8015
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

INCLUDE_PATHS = [
    "app",
    "tests",
    "docs",
    "scripts",
    "deploy",
    "requirements.txt",
    "requirements-dev.txt",
    ".env.example",
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    ".gitignore",
    "data/.gitkeep",
]

EXCLUDE_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".vscode",
    "__pycache__",
    "release_build",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
}

EXCLUDE_NAMES = {
    ".env",
}


@dataclass
class ServerHandle:
    process: subprocess.Popen


def _should_exclude(path: Path) -> bool:
    if path.name in EXCLUDE_NAMES:
        return True

    for part in path.parts:
        if part in EXCLUDE_PARTS:
            return True

    for suffix in EXCLUDE_SUFFIXES:
        if path.name.endswith(suffix):
            return True

    if path.parent.name == "data" and path.name.endswith((".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3")):
        return True

    return False


def _copy_release_tree() -> None:
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    for relative in INCLUDE_PATHS:
        source = REPO_ROOT / relative
        target = STAGING_DIR / relative

        if not source.exists():
            continue

        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            continue

        for file_path in source.rglob("*"):
            if file_path.is_dir():
                continue
            rel_path = file_path.relative_to(REPO_ROOT)
            if _should_exclude(rel_path):
                continue
            out_path = STAGING_DIR / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, out_path)


def _rewrite_env_for_local_smoke() -> None:
    env_example = (STAGING_DIR / ".env.example").read_text(encoding="utf-8")
    lines = []
    replacements = {
        "APP_HOST": SERVER_HOST,
        "APP_PORT": str(SERVER_PORT),
        "HOST": SERVER_HOST,
        "PORT": str(SERVER_PORT),
        "TELEGRAM_ENABLED": "false",
        "TELEGRAM_TIMEZONE": "Europe/Madrid",
        "UVICORN_WORKERS": "1",
    }

    for raw_line in env_example.splitlines():
        line = raw_line
        for key, value in replacements.items():
            prefix = f"{key}="
            if line.startswith(prefix):
                line = f"{key}={value}"
                break
        lines.append(line)

    (STAGING_DIR / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)


def _venv_python_path(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _build_clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _prepare_clean_install() -> dict[str, str]:
    env = _build_clean_env()
    _run([sys.executable, "-m", "venv", ".venv"], cwd=STAGING_DIR, env=env)

    venv_python = _venv_python_path(STAGING_DIR)
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=STAGING_DIR, env=env)
    _run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], cwd=STAGING_DIR, env=env)

    db_init_code = (
        "from app.config import settings;"
        "from app.settings.service import SettingsService;"
        "from app.storage.database import initialize;"
        "initialize(settings.database_path);"
        "svc=SettingsService(settings.database_path,settings.daily_swing_candles_default,settings.backtest_candles_default);"
        "svc.apply_defaults();"
        "print(settings.database_path)"
    )
    _run([str(venv_python), "-c", db_init_code], cwd=STAGING_DIR, env=env)

    return {
        "venv_python": str(venv_python),
    }


def _start_server(venv_python: str) -> ServerHandle:
    stdout_file = (RELEASE_BUILD_DIR / "release_validation_uvicorn.out.log").open("w", encoding="utf-8")
    stderr_file = (RELEASE_BUILD_DIR / "release_validation_uvicorn.err.log").open("w", encoding="utf-8")

    process = subprocess.Popen(
        [
            venv_python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            SERVER_HOST,
            "--port",
            str(SERVER_PORT),
        ],
        cwd=STAGING_DIR,
        stdout=stdout_file,
        stderr=stderr_file,
        text=True,
    )

    deadline = time.time() + 60
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Uvicorn exited before becoming ready")
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=2)
            if response.status_code == 200:
                return ServerHandle(process=process)
        except requests.RequestException:
            pass
        time.sleep(0.5)

    process.terminate()
    raise RuntimeError("Uvicorn did not become healthy in time")


def _stop_server(handle: ServerHandle) -> None:
    process = handle.process
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _request(path: str) -> tuple[int | None, float, str | None]:
    started = time.perf_counter()
    try:
        response = requests.get(f"{BASE_URL}{path}", timeout=15)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return response.status_code, elapsed_ms, None
    except requests.RequestException as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return None, elapsed_ms, exc.__class__.__name__


def _run_smoke_checks() -> dict[str, int]:
    paths = ["/health", "/api/dashboard", "/api/automation/status", "/api/telegram/status"]
    codes: dict[str, int] = {}
    for path in paths:
        code, _, error = _request(path)
        if error is not None:
            raise RuntimeError(f"Smoke check failed for {path}: {error}")
        assert code is not None
        codes[path] = code
    return codes


def _run_api_stress() -> dict[str, float | int]:
    paths = [
        *(["/health"] * 300),
        *(["/api/automation/status"] * 100),
        *(["/api/telegram/status"] * 80),
        *(["/api/dashboard"] * 20),
    ]

    latencies: list[float] = []
    errors = 0
    ok_2xx = 0

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_request, path) for path in paths]
        for future in as_completed(futures):
            status_code, latency_ms, error = future.result()
            latencies.append(latency_ms)
            if error is not None:
                errors += 1
                continue
            if status_code is not None and 200 <= status_code < 300:
                ok_2xx += 1
            else:
                errors += 1

    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = statistics.quantiles(latencies, n=20)[-1] if len(latencies) >= 20 else max(latencies or [0.0])

    return {
        "total_requests": len(paths),
        "ok_2xx": ok_2xx,
        "errors": errors,
        "latency_ms_p50": round(p50, 2),
        "latency_ms_p95": round(p95, 2),
    }


def _run_restart_cycles(venv_python: str) -> dict[str, int]:
    successful_cycles = 0
    for _ in range(3):
        handle = _start_server(venv_python)
        try:
            status = requests.get(f"{BASE_URL}/api/automation/status", timeout=10).json()
            if status.get("running") is True and status.get("interval_seconds") == 300:
                successful_cycles += 1
        finally:
            _stop_server(handle)
    return {"restart_cycles": 3, "successful_cycles": successful_cycles}


def main() -> None:
    RELEASE_BUILD_DIR.mkdir(parents=True, exist_ok=True)

    _copy_release_tree()
    _rewrite_env_for_local_smoke()
    prepared = _prepare_clean_install()

    restart_metrics = _run_restart_cycles(prepared["venv_python"])

    handle = _start_server(prepared["venv_python"])
    try:
        smoke_codes = _run_smoke_checks()
        api_stress = _run_api_stress()
        automation = requests.get(f"{BASE_URL}/api/automation/status", timeout=10).json()
        telegram_status = requests.get(f"{BASE_URL}/api/telegram/status", timeout=10).json()
    finally:
        _stop_server(handle)

    report = {
        "clean_install": {
            "staging_dir": str(STAGING_DIR),
            "smoke_http_codes": smoke_codes,
        },
        "restart_test": restart_metrics,
        "api_stress": api_stress,
        "automation_status_snapshot": automation,
        "telegram_status_snapshot": telegram_status,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
