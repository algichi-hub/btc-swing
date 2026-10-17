"""One-time PostgreSQL administrator enrollment, no secrets in repo/CLI args.

Run interactively on an authorized workstation/secure runner with
BTC_DB_BACKEND=postgres and BTC_DATABASE_URL injected as a secret.
"""
from __future__ import annotations
import getpass
import os
from datetime import datetime, timezone


def provision_admin(username: str, password: str) -> int:
    if os.environ.get("BTC_DB_BACKEND") != "postgres":
        raise RuntimeError("Bootstrap requires BTC_DB_BACKEND=postgres")
    if len(password) < 16:
        raise ValueError("Administrator password must contain at least 16 characters")
    from app.auth.security import hash_password
    from app.storage.postgres import connect_pg
    # Schema migrations belong to the privileged migration owner, never the web role.
    # Bootstrap only enrolls an administrator against an existing Neon schema.
    with connect_pg() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(5022026)")
        row = conn.execute("SELECT count(*) AS n FROM users").fetchone()
        if int(row["n"]) != 0:
            raise RuntimeError("Refusing bootstrap: users already exist")
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO users (username,password_hash,role,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (username, hash_password(password), "ADMIN", 1, now, now),
        )
        return int(cursor.lastrowid)


def main() -> None:
    username = input("Initial admin username: ").strip()
    if not username or len(username) > 64:
        raise ValueError("Invalid username")
    password = getpass.getpass("New admin password (min 16 characters): ")
    password_again = getpass.getpass("Repeat password: ")
    if password != password_again:
        raise ValueError("Password mismatch")
    provision_admin(username, password)
    print("Admin successfully created; password not logged")


if __name__ == "__main__":
    main()