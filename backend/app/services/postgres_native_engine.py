"""Safe orchestration for native PostgreSQL directory-format dump/restore."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import psycopg


@dataclass(frozen=True)
class PgEndpoint:
    host: str
    port: int
    database: str
    username: str
    password: str
    sslmode: str = "prefer"


@dataclass(frozen=True)
class NativeMigrationResult:
    source_server_version: int
    destination_server_version: int
    dump_seconds: float
    restore_seconds: float
    dump_bytes: int
    restore_jobs: int


def _server_version(endpoint: PgEndpoint) -> int:
    with psycopg.connect(
        host=endpoint.host, port=endpoint.port, dbname=endpoint.database,
        user=endpoint.username, password=endpoint.password,
        sslmode=endpoint.sslmode, connect_timeout=10,
        autocommit=True,
    ) as connection:
        return int(connection.execute("SHOW server_version_num").fetchone()[0])


def check_native_compatibility(source: PgEndpoint, destination: PgEndpoint) -> dict:
    """Fail early on unsupported client/server versions or missing binaries."""
    dump_binary = shutil.which("pg_dump")
    restore_binary = shutil.which("pg_restore")
    if not dump_binary or not restore_binary:
        raise RuntimeError(
            "Native PostgreSQL migration requires pg_dump and pg_restore on the worker PATH."
        )
    source_version = _server_version(source)
    destination_version = _server_version(destination)
    client_output = subprocess.run(
        [dump_binary, "--version"], check=True, capture_output=True, text=True
    ).stdout
    try:
        client_major = int(client_output.split()[-1].split(".")[0])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"Could not parse pg_dump version: {client_output.strip()}") from exc
    source_major = source_version // 10000
    destination_major = destination_version // 10000
    if client_major < source_major:
        raise RuntimeError(
            f"pg_dump client major {client_major} is older than source PostgreSQL "
            f"major {source_major}; install a matching or newer client."
        )
    if destination_major < source_major:
        raise RuntimeError(
            f"Native restore from PostgreSQL {source_major} to older destination "
            f"PostgreSQL {destination_major} is not supported by this execution path."
        )
    return {
        "source_server_version": source_version,
        "destination_server_version": destination_version,
        "pg_dump_version": client_output.strip(),
        "pg_dump": dump_binary,
        "pg_restore": restore_binary,
    }


def _assert_destination_empty(endpoint: PgEndpoint) -> None:
    """Native restore is only safe into a fresh destination database."""
    with psycopg.connect(
        host=endpoint.host, port=endpoint.port, dbname=endpoint.database,
        user=endpoint.username, password=endpoint.password,
        sslmode=endpoint.sslmode, connect_timeout=10,
    ) as connection:
        row = connection.execute(
            """
            SELECT count(*)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND n.nspname NOT LIKE 'pg_toast%'
              AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
            """
        ).fetchone()
    if row and row[0]:
        raise RuntimeError(
            "Native pg_restore requires an empty destination database. "
            f"Found {row[0]} existing tables, views, materialized views, sequences, "
            "or foreign tables; use the COPY engine for an existing mapped destination."
        )

def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_process(
    command: list[str],
    env: dict[str, str],
    cancelled: Callable[[], bool] | None,
    progress: Callable[[dict], None] | None,
    stage: str,
) -> float:
    started = time.monotonic()
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name != "nt"),
        creationflags=creation_flags,
    )
    while True:
        if cancelled and cancelled():
            _terminate_process(process)
            raise RuntimeError(f"Native PostgreSQL {stage} cancelled.")
        try:
            stdout, stderr = process.communicate(timeout=1)
            break
        except subprocess.TimeoutExpired:
            if progress:
                progress({"stage": stage, "elapsed_seconds": round(time.monotonic() - started, 2)})
    if process.returncode:
        diagnostic = (stderr or stdout or "No process output.").strip()
        raise RuntimeError(
            f"Native PostgreSQL {stage} failed (exit {process.returncode}): {diagnostic[-4000:]}"
        )
    if progress:
        progress({"stage": stage, "elapsed_seconds": round(time.monotonic() - started, 2), "status": "completed"})
    return time.monotonic() - started


def run_native_migration(
    source: PgEndpoint,
    destination: PgEndpoint,
    *,
    restore_jobs: int = 4,
    dump_jobs: int = 2,
    schemas: list[str] | None = None,
    tables: list[tuple[str, str]] | None = None,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[dict], None] | None = None,
) -> NativeMigrationResult:
    """Dump to a private directory and restore; no credentials enter argv.

    Filtering is explicit. Callers must perform dependency/selection checks
    before passing schemas/tables; a filtered pg_dump does not imply that
    referenced objects are automatically included.
    """
    if not 1 <= restore_jobs <= 16 or not 1 <= dump_jobs <= 8:
        raise ValueError("Native dump/restore jobs are outside safe worker limits.")
    if schemas and tables:
        raise ValueError("Choose schema filtering or table filtering, not both.")
    compatibility = check_native_compatibility(source, destination)
    _assert_destination_empty(destination)
    environment = os.environ.copy()
    environment.update({
        "PGPASSWORD": source.password,
        "PGSSLMODE": source.sslmode,
    })
    dump_args = [
        compatibility["pg_dump"], "--host", source.host, "--port", str(source.port),
        "--username", source.username, "--dbname", source.database,
        "--format=directory", f"--jobs={dump_jobs}", "--no-owner", "--no-acl",
        "--file",
    ]
    with tempfile.TemporaryDirectory(prefix="conduit-pgdump-") as temporary:
        dump_dir = Path(temporary) / "dump"
        dump_args.append(str(dump_dir))
        if schemas:
            for schema in schemas:
                dump_args.extend(["--schema", schema])
        if tables:
            for schema, table in tables:
                dump_args.extend(["--table", f"{schema}.{table}"])
        dump_seconds = _run_process(
            dump_args, environment, cancelled, progress, "dump"
        )
        dump_bytes = sum(path.stat().st_size for path in dump_dir.rglob("*") if path.is_file())

        restore_environment = environment.copy()
        restore_environment.update({
            "PGPASSWORD": destination.password,
            "PGSSLMODE": destination.sslmode,
        })
        restore_args = [
            compatibility["pg_restore"], "--host", destination.host,
            "--port", str(destination.port), "--username", destination.username,
            "--dbname", destination.database, "--no-owner", "--no-acl",
            "--exit-on-error", f"--jobs={restore_jobs}", str(dump_dir),
        ]
        restore_seconds = _run_process(
            restore_args, restore_environment, cancelled, progress, "restore"
        )
    return NativeMigrationResult(
        source_server_version=compatibility["source_server_version"],
        destination_server_version=compatibility["destination_server_version"],
        dump_seconds=dump_seconds,
        restore_seconds=restore_seconds,
        dump_bytes=dump_bytes,
        restore_jobs=restore_jobs,
    )
