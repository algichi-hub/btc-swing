from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.1.0"
ZIP_NAME = f"btc_swing_trade_v{VERSION}_raspberry.zip"
ZIP_PATH = REPO_ROOT / ZIP_NAME
ARCHIVE_ROOT = Path("btc_swing_trade")

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
    ".tmp",
    ".cache",
    ".zip",
}

EXCLUDE_NAMES = {
    ".env",
}


def should_exclude(rel_path: Path) -> bool:
    if rel_path.name in EXCLUDE_NAMES:
        return True

    for part in rel_path.parts:
        if part in EXCLUDE_PARTS:
            return True

    for suffix in EXCLUDE_SUFFIXES:
        if rel_path.name.endswith(suffix):
            return True

    if rel_path.parent.name == "data" and rel_path.name.endswith((".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3")):
        return True

    return False


def collect_files() -> list[Path]:
    files: list[Path] = []
    for relative in INCLUDE_PATHS:
        source = REPO_ROOT / relative
        if not source.exists():
            continue

        if source.is_file():
            rel = source.relative_to(REPO_ROOT)
            if not should_exclude(rel):
                files.append(rel)
            continue

        for file_path in source.rglob("*"):
            if file_path.is_dir():
                continue
            rel = file_path.relative_to(REPO_ROOT)
            if should_exclude(rel):
                continue
            files.append(rel)

    return sorted(set(files))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    files = collect_files()

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel in files:
            archive.write(REPO_ROOT / rel, (ARCHIVE_ROOT / rel).as_posix())

    report = {
        "zip_path": str(ZIP_PATH),
        "zip_size_bytes": ZIP_PATH.stat().st_size,
        "sha256": sha256(ZIP_PATH),
        "file_count": len(files),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
