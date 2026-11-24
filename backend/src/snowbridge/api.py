"""Snowbridge demo API and PostgreSQL snapshot vertical slice.

This API is intended for local demonstration. Job state is process-local;
production deployment must move job state and credentials to durable,
authenticated services before exposing it to a network.
"""
from __future__ import annotations

import hashlib
import threading
import traceback
import uuid
from dataclasses import asdict
from typing import Any
from urllib.parse import quote

import psycopg
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from snowbridge.adapters.postgresql import PostgresAdapter, PostgresEndpoint
from snowbridge.connection_manager import ConnectionManager, ConnectionSpec
from snowbridge.contracts import SecretReference
from snowbridge.bulk_copy import copy_binary_table
from snowbridge.discovery import discover_inventory
from snowbridge.schema_ddl import apply_postgresql_ddl
from snowbridge.snapshot import ExportedSnapshot
from snowbridge.target_commit import commit_chunk


app = FastAPI(
    title="Snowbridge Migration API",
    version="0.3.0",
    description="Database discovery and PostgreSQL snapshot migration demo API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
CONNECTIONS: dict[str, dict[str, Any]] = {}
CONNECTIONS_LOCK = threading.Lock()


class ConnectionInput(BaseModel):
    engine: str = "postgresql"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=2048)
    tls: bool = False


class DiscoveryRequest(BaseModel):
    connection: ConnectionInput
    schemas: list[str] | None = None


class MigrationRequest(BaseModel):
    source: ConnectionInput
    target: ConnectionInput
    schemas: list[str] | None = None
    block_bytes: int = Field(default=1048576, ge=65536, le=16777216)


class SavedConnectionRequest(BaseModel):
    connection: ConnectionInput
    name: str = Field(default="Database connection", min_length=1, max_length=100)


@app.get("/api/connections")
def list_connections() -> list[dict[str, Any]]:
    with CONNECTIONS_LOCK:
        return [
            {"id": key, "name": item["name"], "engine": item["connection"].engine,
             "host": item["connection"].host, "port": item["connection"].port,
             "database": item["connection"].database, "username": item["connection"].username,
             "tls": item["connection"].tls}
            for key, item in CONNECTIONS.items()
        ]


@app.post("/api/connections")
def add_connection(request: SavedConnectionRequest) -> dict[str, str]:
    connection_id = str(uuid.uuid4())
    with CONNECTIONS_LOCK:
        CONNECTIONS[connection_id] = {"name": request.name, "connection": request.connection}
    return {"id": connection_id, "status": "saved_in_session"}


@app.delete("/api/connections/{connection_id}")
def remove_connection(connection_id: str) -> dict[str, str]:
    with CONNECTIONS_LOCK:
        if CONNECTIONS.pop(connection_id, None) is None:
            raise HTTPException(404, "Connection not found in this API session.")
    return {"id": connection_id, "status": "removed"}


def _dsn(value: ConnectionInput) -> str:
    if value.engine.lower() not in {"postgres", "postgresql"}:
        raise HTTPException(400, "The executable snapshot pipeline currently supports PostgreSQL endpoints only.")
    return (
        f"postgresql://{quote(value.username, safe='')}:{quote(value.password, safe='')}"
        f"@{value.host}:{value.port}/{quote(value.database, safe='')}"
        f"?connect_timeout=10&sslmode={'require' if value.tls else 'prefer'}"
    )


class _RequestSecretProvider:
    """Ephemeral provider; request credentials are never written to disk or logs."""
    def __init__(self, password: str):
        self.password = password

    def resolve(self, reference: SecretReference) -> dict[str, str]:
        return {"password": self.password}


def _adapter(value: ConnectionInput):
    spec = ConnectionSpec(
        connection_id="request-only",
        engine=value.engine,
        host=value.host,
        database=value.database,
        username=value.username,
        secret_ref=SecretReference("ephemeral", "request-only"),
        port=value.port,
        tls_required=value.tls,
    )
    return ConnectionManager(_RequestSecretProvider(value.password)).create_adapter(spec)


def _json(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, tuple):
        return [_json(v) for v in value]
    if isinstance(value, list):
        return [_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {k: _json(v) for k, v in asdict(value).items()}
    return value


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "snowbridge-api", "version": "0.3.0"}


@app.post("/api/connections/test")
def test_connection(request: DiscoveryRequest) -> dict[str, Any]:
    try:
        adapter = _adapter(request.connection)
        capabilities = adapter.inspect_capabilities()
        with adapter.connect() as conn:
            if request.connection.engine.lower() in {"postgres", "postgresql"}:
                row = conn.execute("SELECT current_database(), version()").fetchone()
                database, version = row[0], row[1]
            elif request.connection.engine.lower() == "mysql":
                cursor = conn.cursor()
                cursor.execute("SELECT DATABASE(), VERSION()")
                database, version = cursor.fetchone()
                cursor.close()
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), version FROM product_component_version WHERE product LIKE 'Oracle Database%'")
                row = cursor.fetchone()
                database, version = (row[0], row[1]) if row else (request.connection.database, "Oracle")
                cursor.close()
        return {
            "connected": True,
            "engine": request.connection.engine.lower(),
            "database": database,
            "server_version": version,
            "capabilities": [_json(c) for c in capabilities],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Connection failed: {type(exc).__name__}: {str(exc)[:500]}") from exc


@app.post("/api/discovery")
def discover(request: DiscoveryRequest) -> dict[str, Any]:
    try:
        adapter = _adapter(request.connection)
        inventory = discover_inventory(adapter, request.connection.engine, schemas=request.schemas)
        return {
            "engine": inventory.engine,
            "captured_at": inventory.captured_at.isoformat(),
            "tables": [_json(t) for t in inventory.tables],
            "capabilities": [_json(c) for c in inventory.capabilities],
            "warnings": list(inventory.warnings),
            "estimate": _json(inventory.estimate),
            "table_count": len(inventory.tables),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Discovery failed: {type(exc).__name__}: {str(exc)[:700]}") from exc


@app.post("/api/migrations")
def start_migration(request: MigrationRequest, background: BackgroundTasks) -> dict[str, str]:
    if request.source.engine.lower() not in {"postgres", "postgresql"} or request.target.engine.lower() not in {"postgres", "postgresql"}:
        raise HTTPException(400, "The executable pipeline currently supports PostgreSQL-to-PostgreSQL only.")
    if (request.source.host, request.source.port, request.source.database) == (
        request.target.host, request.target.port, request.target.database
    ):
        raise HTTPException(400, "Source and target must be different database endpoints.")
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "status": "queued", "stage": "Queued",
            "completed_tables": 0, "total_tables": 0, "rows": 0,
            "bytes": 0, "results": [], "error": None,
        }
    background.add_task(_execute_migration, job_id, request)
    return {"id": job_id, "status": "queued"}


@app.get("/api/migrations/{job_id}")
def migration_status(job_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Migration job not found. Demo job state is lost when the API process restarts.")
        return dict(job)


def _update_job(job_id: str, **changes: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(changes)


def _execute_migration(job_id: str, request: MigrationRequest) -> None:
    try:
        source = _adapter(request.source)
        target = _adapter(request.target)
        _update_job(job_id, status="running", stage="Inspecting source schema")
        inventory = discover_inventory(source, "postgresql", schemas=request.schemas)
        if not inventory.tables:
            raise RuntimeError("No accessible base tables were discovered in the selected schemas.")
        _update_job(job_id, total_tables=len(inventory.tables), stage="Checking target compatibility")
        with source.connect() as source_version_conn:
            source_major = int(source_version_conn.execute("SHOW server_version_num").fetchone()[0]) // 10000
        with target.connect() as target_version_conn:
            target_major = int(target_version_conn.execute("SHOW server_version_num").fetchone()[0]) // 10000
        if source_major != target_major:
            raise RuntimeError("Binary COPY demo requires matching PostgreSQL major versions; use a logical row-transfer path for cross-major migrations.")

        # Create target schemas/tables before data transfer. Existing target
        # tables must be empty: never truncate or silently overwrite user data.
        _update_job(job_id, stage="Preparing target DDL")
        with target.connect() as target_conn:
            ddl_plan = apply_postgresql_ddl(target_conn, inventory.tables)
            for schema_name, table_name, _columns in ddl_plan.load_columns:
                from psycopg import sql
                has_rows = target_conn.execute(
                    sql.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(
                        sql.Identifier(schema_name, table_name)
                    )
                ).fetchone()[0]
                if has_rows:
                    raise RuntimeError(
                        f"Target table {schema_name}.{table_name} is not empty. "
                        "The demo pipeline refuses to append duplicate data or truncate existing rows."
                    )
        _update_job(job_id, stage="Transferring consistent snapshot", ddl_diagnostics=list(ddl_plan.diagnostics))

        results = []
        total_rows = 0
        total_bytes = 0
        with ExportedSnapshot(source) as snapshot:
            for table in inventory.tables:
                writable = tuple(c.name for c in sorted(table.columns, key=lambda c: c.ordinal)
                                 if not c.generated_kind)
                if not writable:
                    results.append({"table": f"{table.schema_name}.{table.table_name}", "rows": 0, "bytes": 0, "status": "skipped-no-writable-columns"})
                    continue
                _update_job(job_id, stage=f"Copying {table.schema_name}.{table.table_name}")
                chunk_id = f"{job_id}:{table.schema_name}.{table.table_name}"
                digest = hashlib.sha256(
                    f"{snapshot.snapshot_id}|{table.schema_name}|{table.table_name}|{','.join(writable)}".encode()
                ).hexdigest()
                with source.connect() as source_conn, target.connect() as target_conn:
                    ExportedSnapshot(source, handle=snapshot).import_into(source_conn)

                    def apply(conn: Any):
                        return copy_binary_table(
                            source_conn, conn,
                            source_schema=table.schema_name, source_table=table.table_name,
                            target_schema=table.schema_name, target_table=table.table_name,
                            columns=writable, block_bytes=request.block_bytes,
                        )

                    receipt = commit_chunk(
                        target_conn, chunk_id=chunk_id, payload_digest=digest, apply=apply
                    )
                total_rows += receipt.committed_rows
                total_bytes += receipt.committed_bytes
                result = {
                    "table": f"{table.schema_name}.{table.table_name}",
                    "rows": receipt.committed_rows,
                    "bytes": receipt.committed_bytes,
                    "replayed": receipt.already_committed,
                    "status": "completed",
                }
                results.append(result)
                _update_job(
                    job_id, completed_tables=len(results), rows=total_rows,
                    bytes=total_bytes, results=list(results),
                )
        _update_job(
            job_id, status="completed", stage="Snapshot transfer completed",
            completed_tables=len(inventory.tables), rows=total_rows,
            bytes=total_bytes, results=results,
            note="Snapshot-only PostgreSQL transfer. CDC, durable API job state, automatic reconciliation and cutover are not included.",
        )
    except Exception as exc:
        _update_job(
            job_id, status="failed", stage="Migration failed",
            error=f"{type(exc).__name__}: {str(exc)[:1200]}",
        )
