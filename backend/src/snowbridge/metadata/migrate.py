"""Apply ordered SQL metadata migrations with a PostgreSQL advisory lock."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import psycopg

from snowbridge.config import Settings


def resolve_dsn(explicit_dsn: str | None) -> str:
    """Prefer --dsn; otherwise use the same environment/.env settings as the app."""
    if explicit_dsn and explicit_dsn.strip():
        return explicit_dsn.strip()
    configured = Settings.from_env().metadata_database_url
    if configured and configured.strip():
        return configured.strip()
    raise ValueError(
        "metadata DSN is missing; set SNOWBRIDGE_METADATA_DATABASE_URL "
        "in backend/.env or pass --dsn"
    )


def apply_migrations(dsn: str, directory: Path) -> list[str]:
    applied_now: list[str] = []
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('snowbridge_metadata_migrations'))")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snowbridge_schema_migrations (
                version text PRIMARY KEY,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        existing = {row[0]: row[1] for row in conn.execute(
            "SELECT version, checksum FROM snowbridge_schema_migrations"
        ).fetchall()}
        for path in files:
            version = path.name
            body = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if version in existing:
                if existing[version] != checksum:
                    raise RuntimeError(f"applied migration {version} checksum changed")
                continue
            # Each migration and its ledger insert share this connection transaction.
            conn.execute(body)
            conn.execute(
                "INSERT INTO snowbridge_schema_migrations(version, checksum) VALUES (%s, %s)",
                (version, checksum),
            )
            applied_now.append(version)
    return applied_now


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Snowbridge metadata SQL migrations")
    parser.add_argument(
        "--dsn",
        help="metadata PostgreSQL DSN (defaults to SNOWBRIDGE_METADATA_DATABASE_URL/.env)",
    )
    parser.add_argument("--directory", type=Path,
                        default=Path(__file__).resolve().parents[3] / "sql")
    args = parser.parse_args()
    try:
        dsn = resolve_dsn(args.dsn)
    except ValueError as exc:
        parser.error(str(exc))
    for version in apply_migrations(dsn, args.directory):
        print(f"applied {version}")
    print("metadata schema is up to date")


if __name__ == "__main__":
    main()
