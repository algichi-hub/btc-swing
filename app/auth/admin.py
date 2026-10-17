from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable
from pathlib import Path

from app.auth.models import UserRole
from app.auth.security import MIN_PASSWORD_LENGTH, normalize_username
from app.auth.service import AuthService
from app.config import settings
from app.storage.database import initialize


def create_user_cli(
    username: str,
    role: str = UserRole.ADMIN.value,
    db_path: Path | None = None,
    password_getter: Callable[[str], str] | None = None,
) -> int:
    """Creates a user via interactive CLI.

    Password must be entered interactively via getpass (or a provided callable for tests).
    Plaintext password flags are strictly disallowed.
    """
    getter = password_getter or getpass.getpass
    target_db = db_path or settings.database_path

    try:
        canonical_username = normalize_username(username)
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    # Ensure DB schema is initialized
    initialize(target_db)
    service = AuthService(db_path=target_db)

    # Check for existing user before prompting for password
    existing_user = service.get_user_by_username(canonical_username)
    if existing_user is not None:
        sys.stderr.write(f"Error: Username '{canonical_username}' already exists.\n")
        return 1

    try:
        pw1 = getter("Password: ")
        if len(pw1) < MIN_PASSWORD_LENGTH:
            sys.stderr.write(
                f"Error: Password must be at least {MIN_PASSWORD_LENGTH} characters long.\n"
            )
            return 1

        pw2 = getter("Confirm password: ")
        if pw1 != pw2:
            sys.stderr.write("Error: Passwords do not match.\n")
            return 1

        user = service.create_user(username=username, password=pw1, role=role)
        sys.stdout.write(f"Success: User '{user.username}' created with role '{user.role}'.\n")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.auth.admin",
        description="Local administrative CLI for BTC Swing Trade V4",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-user", help="Create a new user")
    create_parser.add_argument("--username", required=True, help="Username for the new account")
    create_parser.add_argument(
        "--role",
        default=UserRole.ADMIN.value,
        choices=[UserRole.ADMIN.value, UserRole.VIEWER.value],
        help="Role for the account (default: ADMIN)",
    )
    create_parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Path to SQLite database (default: from configuration)",
    )
    return parser


def main(argv: list[str] | None = None, password_getter: Callable[[str], str] | None = None) -> int:
    args_list = argv if argv is not None else sys.argv[1:]

    # Explicit security check: forbid passing passwords on command line
    for arg in args_list:
        if arg.startswith("--password"):
            sys.stderr.write(
                "Security Error: Passing passwords via command-line arguments is forbidden.\n"
                "Passwords must be entered interactively.\n"
            )
            return 2

    parser = build_parser()
    try:
        parsed = parser.parse_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    if parsed.command == "create-user":
        return create_user_cli(
            username=parsed.username,
            role=parsed.role,
            db_path=parsed.database,
            password_getter=password_getter,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
