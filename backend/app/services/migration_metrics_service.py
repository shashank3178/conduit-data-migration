"""Idempotent migration metrics and PostgreSQL storage measurements."""
import hashlib
import json
from datetime import UTC, datetime

import psycopg

from sqlalchemy import func

from app.models.migration_metrics import (
    MigrationBatchMetric,
    MigrationDatabaseMetric,
    MigrationRunMetric,
    MigrationTableMetric,
)


def logical_payload_bytes(rows) -> int:
    """Return UTF-8 JSON payload size; this is not a network-byte measurement."""
    return sum(
        len(json.dumps(row, default=str, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        for row in rows
    )


def batch_identity(run_table_id, checkpoint_start, checkpoint_end) -> str:
    payload = json.dumps(
        [str(run_table_id), checkpoint_start, checkpoint_end],
        default=str, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_run_metric(db, run):
    metric = db.query(MigrationRunMetric).filter_by(run_id=run.id).one_or_none()
    if metric is None:
        metric = MigrationRunMetric(run_id=run.id, started_at=run.started_at or datetime.now(UTC))
        db.add(metric)
        db.flush()
    return metric


def record_committed_batch(
    db, run, progress, rows, inserted, updated, skipped, failed,
    checkpoint_start, checkpoint_end, duration_ms,
):
    """Persist one committed batch in the same metadata transaction as its checkpoint."""
    key = batch_identity(progress.id, checkpoint_start, checkpoint_end)
    existing = db.query(MigrationBatchMetric).filter_by(run_id=run.id, batch_key=key).one_or_none()
    if existing is not None:
        return existing

    logical_bytes = logical_payload_bytes(rows)
    sequence = (
        db.query(func.coalesce(func.max(MigrationBatchMetric.sequence), 0))
        .filter_by(run_table_id=progress.id).scalar() or 0
    ) + 1
    db.add(MigrationBatchMetric(
        run_id=run.id,
        run_table_id=progress.id,
        batch_key=key,
        sequence=sequence,
        rows_fetched=len(rows),
        rows_inserted=inserted,
        rows_updated=updated,
        rows_skipped=skipped,
        rows_failed=failed,
        logical_bytes=logical_bytes,
        duration_ms=duration_ms,
        checkpoint_start=checkpoint_start,
        checkpoint_end=checkpoint_end,
    ))

    committed = inserted + updated
    run_metric = ensure_run_metric(db, run)
    run_metric.rows_fetched += len(rows)
    run_metric.rows_committed += committed
    run_metric.batches_committed += 1
    run_metric.logical_bytes += logical_bytes
    run_metric.processing_duration_ms += duration_ms
    seconds = run_metric.processing_duration_ms / 1000
    run_metric.rows_per_second = run_metric.rows_committed / seconds if seconds else 0
    run_metric.logical_bytes_per_second = run_metric.logical_bytes / seconds if seconds else 0

    table_metric = db.query(MigrationTableMetric).filter_by(run_table_id=progress.id).one_or_none()
    if table_metric is None:
        table_metric = MigrationTableMetric(run_id=run.id, run_table_id=progress.id)
        db.add(table_metric)
    table_metric.rows_fetched += len(rows)
    table_metric.rows_committed += committed
    table_metric.batches_committed += 1
    table_metric.logical_bytes += logical_bytes
    return key


def _database_size(connection):
    try:
        with connection.transaction():
            row = connection.execute("SELECT pg_database_size(current_database())").fetchone()
        return int(row[0]) if row else None
    except psycopg.Error:  # Metrics must not fail a data migration.
        return None


def record_database_snapshot(db, run, connection_record, role, connection):
    size = _database_size(connection)
    if size is None:
        return
    db.add(MigrationDatabaseMetric(
        run_id=run.id,
        connection_id=connection_record.id,
        role=role,
        database_name=connection_record.database,
        physical_bytes=size,
        measurement_kind="exact",
    ))


def _relation_size(connection, schema, table):
    try:
        with connection.transaction():
            row = connection.execute(
                "SELECT pg_total_relation_size(format('%I.%I', %s, %s)::regclass)",
                (schema, table),
            ).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except psycopg.Error:  # A missing relation or insufficient catalog privilege is non-fatal.
        return None

def record_table_storage_snapshot(db, run, progress, source, destination):
    source_size = _relation_size(source, progress.source_schema, progress.source_table)
    destination_size = _relation_size(destination, progress.destination_schema, progress.destination_table)
    metric = db.query(MigrationTableMetric).filter_by(run_table_id=progress.id).one_or_none()
    if metric is None:
        metric = MigrationTableMetric(run_id=run.id, run_table_id=progress.id)
        db.add(metric)
    metric.source_physical_bytes = source_size
    metric.destination_physical_bytes = destination_size
    metric.storage_measured_at = datetime.now(UTC)


def finish_run_metric(db, run):
    metric = ensure_run_metric(db, run)
    metric.finished_at = run.finished_at or datetime.now(UTC)
