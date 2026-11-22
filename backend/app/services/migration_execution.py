"""Durable keyset-paginated PostgreSQL migration execution."""
import logging
import time
import uuid
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from decimal import Decimal
from uuid import UUID as PyUUID

logger = logging.getLogger(__name__)

import psycopg
from psycopg import sql
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.connection import DatabaseConnection
from app.models.migration_plan import MigrationColumnMapping, MigrationPlan, MigrationPlanTable
from app.models.migration_run import (
    MigrationRowError,
    MigrationRun,
    MigrationRunEvent,
    MigrationRunTable,
)
from app.services.connection_service import decrypt_password
from app.services.migration_metrics_service import (
    ensure_run_metric,
    finish_run_metric,
    record_committed_batch,
    record_database_snapshot,
    record_table_storage_snapshot,
)


def _event(db, run, event_type, run_table=None, **details):
    db.add(MigrationRunEvent(run_id=run.id, run_table_id=run_table.id if run_table else None, event_type=event_type, details=details))


def _connect(record: DatabaseConnection):
    return psycopg.connect(
        host=record.host, port=record.port, dbname=record.database, user=record.username,
        password=decrypt_password(record.password_encrypted), sslmode=record.sslmode,
        connect_timeout=10, application_name="Conduit migration",
    )


def _cancel_requested(run_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        run = db.get(MigrationRun, run_id)
        return run is None or run.status == "cancel_requested"


def _json_key(values):
    result = []
    for value in values:
        if isinstance(value, (datetime, date, datetime_time)):
            result.append(value.isoformat())
        elif isinstance(value, (Decimal, PyUUID)):
            result.append(str(value))
        elif value is None or isinstance(value, (str, int, float, bool)):
            result.append(value)
        else:
            raise ValueError(f"Unsupported checkpoint key type: {type(value).__name__}")
    return result


def _restore_key(values, columns):
    restored = []
    for value, column in zip(values, columns, strict=True):
        kind = str(column.get("type", "")).upper()
        if value is None:
            raise ValueError("Primary-key checkpoint cannot contain NULL.")
        if any(token in kind for token in ("INT", "SERIAL")):
            restored.append(int(value))
        elif any(token in kind for token in ("NUMERIC", "DECIMAL")):
            restored.append(Decimal(str(value)))
        elif "UUID" in kind:
            restored.append(PyUUID(str(value)))
        elif kind == "DATE":
            restored.append(date.fromisoformat(value))
        elif "TIMESTAMP" in kind:
            restored.append(datetime.fromisoformat(value))
        elif "BOOL" in kind:
            restored.append(bool(value))
        elif any(token in kind for token in ("REAL", "FLOAT", "DOUBLE")):
            restored.append(float(value))
        elif kind.startswith("TIME"):
            restored.append(datetime_time.fromisoformat(value))
        elif any(token in kind for token in ("CHAR", "TEXT", "NAME")):
            restored.append(str(value))
        else:
            raise ValueError(f"Unsupported primary-key type for resumable execution: {kind}")
    return tuple(restored)


def _tuple_sql(columns):
    return sql.SQL("({})").format(sql.SQL(", ").join(map(sql.Identifier, columns)))


def _fetch_upper_key(source, table, pk_columns):
    order_by = sql.SQL(", ").join(
        sql.SQL("{} DESC").format(sql.Identifier(name))
        for name in pk_columns
    )
    query = sql.SQL("SELECT {} FROM {}.{} ORDER BY {} LIMIT 1").format(
        sql.SQL(", ").join(map(sql.Identifier, pk_columns)),
        sql.Identifier(table.source_schema),
        sql.Identifier(table.source_table),
        order_by,
    )
    row = source.execute(query).fetchone()
    return tuple(row) if row else None


def _fetch_batch(source, table, pk_columns, source_columns, batch_size, last_key, upper_key):
    predicates = []
    params = []
    key_tuple = _tuple_sql(pk_columns)
    placeholders = sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() for _ in pk_columns))
    if last_key is not None:
        predicates.append(sql.SQL("{} > {}").format(key_tuple, placeholders))
        params.extend(last_key)
    predicates.append(sql.SQL("{} <= {}").format(key_tuple, placeholders))
    params.extend(upper_key)
    query = sql.SQL("SELECT {} FROM {}.{} WHERE {} ORDER BY {} LIMIT %s").format(
        sql.SQL(", ").join(map(sql.Identifier, source_columns)),
        sql.Identifier(table.source_schema), sql.Identifier(table.source_table),
        sql.SQL(" AND ").join(predicates),
        sql.SQL(", ").join(map(sql.Identifier, pk_columns)),
    )
    params.append(batch_size)
    return source.execute(query, params).fetchall()


def _write_batch(destination, table, destination_columns, conflict_columns, rows, strategy):
    if not rows:
        return 0, 0, 0
    width = len(destination_columns)
    values_sql = sql.SQL(", ").join(
        sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() for _ in range(width)))
        for _ in rows
    )
    query = sql.SQL("INSERT INTO {}.{} ({}) VALUES {}").format(
        sql.Identifier(table.destination_schema), sql.Identifier(table.destination_table),
        sql.SQL(", ").join(map(sql.Identifier, destination_columns)), values_sql,
    )
    flat_values = [value for row in rows for value in row]
    if strategy == "UPSERT":
        update_columns = [name for name in destination_columns if name not in conflict_columns]
        if update_columns:
            assignments = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(name), sql.Identifier(name))
                for name in update_columns
            )
            changed = sql.SQL(" OR ").join(
                sql.SQL("{}.{} IS DISTINCT FROM EXCLUDED.{}").format(
                    sql.Identifier(table.destination_table), sql.Identifier(name), sql.Identifier(name)
                )
                for name in update_columns
            )
            query += sql.SQL(" ON CONFLICT ({}) DO UPDATE SET {} WHERE {}").format(
                sql.SQL(", ").join(map(sql.Identifier, conflict_columns)), assignments, changed,
            )
        else:
            query += sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
                sql.SQL(", ").join(map(sql.Identifier, conflict_columns))
            )
        query += sql.SQL(" RETURNING (xmax = 0)")
        returned = destination.execute(query, flat_values).fetchall()
        inserted = sum(1 for row in returned if row[0])
        updated = len(returned) - inserted
        return inserted, updated, len(rows) - len(returned)
    query += sql.SQL(" ON CONFLICT DO NOTHING RETURNING 1")
    inserted = len(destination.execute(query, flat_values).fetchall())
    return inserted, 0, len(rows) - inserted


def _execution_error_detail(exc: Exception) -> str:
    """Return actionable database diagnostics without exposing connection credentials."""
    if isinstance(exc, psycopg.Error):
        primary = getattr(getattr(exc, "diag", None), "message_primary", None)
        state = getattr(exc, "sqlstate", None)
        detail = primary or "PostgreSQL operation failed."
        prefix = f"SQLSTATE {state}: " if state else ""
        return f"{prefix}{detail}"[:1000]
    return str(exc)[:1000] or type(exc).__name__


def _record_row_error(db, run, progress, key, key_columns, exc):
    source_key = {name: value for name, value in zip(key_columns, _json_key(key), strict=True)}
    existing = db.query(MigrationRowError).filter_by(
        run_table_id=progress.id, source_key=source_key, resolved_at=None
    ).first()
    if existing:
        existing.attempts += 1
        existing.error_type = type(exc).__name__
        existing.error_message = _execution_error_detail(exc)
    else:
        db.add(MigrationRowError(
            run_id=run.id, run_table_id=progress.id, source_key=source_key,
            error_type=type(exc).__name__,
            error_message=_execution_error_detail(exc),
            attempts=1,
        ))


def _is_row_level_write_error(exc: psycopg.Error) -> bool:
    """Only isolate data/integrity failures; schema, permission and SQL errors fail the run."""
    state = getattr(exc, "sqlstate", None) or ""
    return state.startswith(("22", "23"))


def _write_with_isolation(destination, db, run, progress, table, destination_columns,
                          conflict_columns, key_columns, rows, keys, strategy):
    try:
        with destination.transaction():
            result = _write_batch(destination, table, destination_columns, conflict_columns, rows, strategy)
        return (*result, 0, [])
    except psycopg.OperationalError:
        raise
    except psycopg.Error as exc:
        if not _is_row_level_write_error(exc):
            raise
        inserted = updated = skipped = failed = 0
        failed_keys = []
        with destination.transaction():
            for row, key in zip(rows, keys, strict=True):
                try:
                    with destination.transaction():
                        outcome = _write_batch(destination, table, destination_columns, conflict_columns, [row], strategy)
                    inserted += outcome[0]
                    updated += outcome[1]
                    skipped += outcome[2]
                except psycopg.OperationalError:
                    raise
                except psycopg.Error as exc:
                    failed += 1
                    failed_keys.append(key)
                    _record_row_error(db, run, progress, key, key_columns, exc)
        return inserted, updated, skipped, failed, failed_keys


def _cursor_rows(cursor, size):
    while True:
        rows = cursor.fetchmany(size)
        if not rows:
            return
        yield from rows


def _validation_values_equal(source_value, destination_value):
    """Compare values without Python's bool/int and NaN equality traps."""
    if isinstance(source_value, bool) or isinstance(destination_value, bool):
        return type(source_value) is type(destination_value) and source_value == destination_value
    if isinstance(source_value, float) and isinstance(destination_value, float):
        if source_value != source_value and destination_value != destination_value:
            return True
    if isinstance(source_value, Decimal) and isinstance(destination_value, Decimal):
        if source_value.is_nan() and destination_value.is_nan():
            return True
    if isinstance(source_value, memoryview):
        source_value = source_value.tobytes()
    if isinstance(destination_value, memoryview):
        destination_value = destination_value.tobytes()
    return source_value == destination_value


def _validation_key_payload(key, key_columns):
    return {
        name: value
        for name, value in zip(key_columns, _json_key(key), strict=True)
    }


def _validate_table_detailed(
    source, destination, table, source_columns, destination_columns,
    source_pk, destination_pk, batch_size, sample_limit=20,
):
    """Stream-compare rows and return actionable, bounded validation diagnostics."""
    source_query = sql.SQL("SELECT {} FROM {}.{} ORDER BY {}").format(
        sql.SQL(", ").join(map(sql.Identifier, source_columns)),
        sql.Identifier(table.source_schema), sql.Identifier(table.source_table),
        sql.SQL(", ").join(map(sql.Identifier, source_pk)),
    )
    destination_query = sql.SQL("SELECT {} FROM {}.{} ORDER BY {}").format(
        sql.SQL(", ").join(map(sql.Identifier, destination_columns)),
        sql.Identifier(table.destination_schema), sql.Identifier(table.destination_table),
        sql.SQL(", ").join(map(sql.Identifier, destination_pk)),
    )
    source_key_indexes = [source_columns.index(name) for name in source_pk]
    destination_key_indexes = [destination_columns.index(name) for name in destination_pk]
    details = {
        "source_rows": 0,
        "destination_rows": 0,
        "missing_in_destination": 0,
        "extra_in_destination": 0,
        "changed_rows": 0,
        "mismatch_rows": 0,
        "samples": [],
        "sample_limit": sample_limit,
        "comparison": "primary-key ordered streaming comparison",
    }

    def add_sample(reason, key, columns=None, type_differences=None):
        if len(details["samples"]) >= sample_limit:
            return
        sample = {
            "reason": reason,
            "primary_key": _validation_key_payload(key, source_pk),
        }
        if columns:
            sample["different_columns"] = columns
        if type_differences:
            sample["python_type_differences"] = type_differences
        details["samples"].append(sample)

    with source.cursor(name=f"validate_src_{uuid.uuid4().hex[:16]}") as left, destination.cursor(
        name=f"validate_dst_{uuid.uuid4().hex[:16]}"
    ) as right:
        left.execute(source_query)
        right.execute(destination_query)
        source_rows = iter(_cursor_rows(left, batch_size))
        destination_rows = iter(_cursor_rows(right, batch_size))
        source_row = next(source_rows, None)
        destination_row = next(destination_rows, None)
        while source_row is not None or destination_row is not None:
            if source_row is None:
                details["destination_rows"] += 1
                destination_key = tuple(destination_row[index] for index in destination_key_indexes)
                details["extra_in_destination"] += 1
                add_sample("EXTRA_IN_DESTINATION", destination_key)
                destination_row = next(destination_rows, None)
                continue
            if destination_row is None:
                details["source_rows"] += 1
                source_key = tuple(source_row[index] for index in source_key_indexes)
                details["missing_in_destination"] += 1
                add_sample("MISSING_IN_DESTINATION", source_key)
                source_row = next(source_rows, None)
                continue

            details["source_rows"] += 1
            details["destination_rows"] += 1
            source_key = tuple(source_row[index] for index in source_key_indexes)
            destination_key = tuple(destination_row[index] for index in destination_key_indexes)
            try:
                source_before_destination = source_key < destination_key
                destination_before_source = destination_key < source_key
            except TypeError as exc:
                raise ValueError(
                    "Validation cannot order source and destination primary keys. "
                    f"Source key types: {[type(value).__name__ for value in source_key]}; "
                    f"destination key types: {[type(value).__name__ for value in destination_key]}. "
                    "Check that mapped primary-key columns use order-compatible PostgreSQL types."
                ) from exc

            if source_before_destination:
                details["missing_in_destination"] += 1
                add_sample("MISSING_IN_DESTINATION", source_key)
                source_row = next(source_rows, None)
            elif destination_before_source:
                details["extra_in_destination"] += 1
                add_sample("EXTRA_IN_DESTINATION", destination_key)
                destination_row = next(destination_rows, None)
            else:
                different_columns = []
                type_differences = {}
                for index, (source_value, destination_value) in enumerate(
                    zip(source_row, destination_row, strict=True)
                ):
                    if not _validation_values_equal(source_value, destination_value):
                        column_name = source_columns[index]
                        different_columns.append(column_name)
                        if type(source_value) is not type(destination_value):
                            type_differences[column_name] = {
                                "source": type(source_value).__name__,
                                "destination": type(destination_value).__name__,
                            }
                if different_columns:
                    details["changed_rows"] += 1
                    reason = "TYPE_MISMATCH" if type_differences else "COLUMN_VALUE_MISMATCH"
                    add_sample(reason, source_key, different_columns, type_differences or None)
                source_row = next(source_rows, None)
                destination_row = next(destination_rows, None)

    # Named/server-side cursors open implicit transactions. End both read
    # transactions here: otherwise the next table's writer can run inside a
    # savepoint, appear committed, and then be rolled back when the connection
    # closes. This boundary is essential because one worker reuses connections
    # across multiple tables.
    for connection in (source, destination):
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    details["mismatch_rows"] = (
        details["missing_in_destination"]
        + details["extra_in_destination"]
        + details["changed_rows"]
    )
    details["matched_rows"] = (
        min(details["source_rows"], details["destination_rows"])
        - details["missing_in_destination"]
        - details["extra_in_destination"]
        - details["changed_rows"]
    )
    return details


def _validate_table(source, destination, table, source_columns, destination_columns,
                    source_pk, destination_pk, batch_size):
    """Backward-compatible mismatch-count wrapper for callers and tests."""
    return _validate_table_detailed(
        source, destination, table, source_columns, destination_columns,
        source_pk, destination_pk, batch_size,
    )["mismatch_rows"]

def execute_run(run_id: uuid.UUID, worker_id: str | None = None) -> None:
    source = destination = None
    with SessionLocal() as db:
        run = db.get(MigrationRun, run_id)
        if not run or run.status not in {"queued", "running"}:
            return
        plan = db.get(MigrationPlan, run.plan_id)
        if not plan:
            run.status, run.error_message = "failed", "Migration plan no longer exists."
            run.finished_at = datetime.now(UTC)
            db.commit()
            return
        run.status = "running"
        run.worker_id = worker_id or run.worker_id
        run.started_at = run.started_at or datetime.now(UTC)
        run.heartbeat_at = datetime.now(UTC)
        _event(db, run, "worker_started", worker_id=run.worker_id, write_strategy=run.write_strategy, batch_size=run.batch_size)
        ensure_run_metric(db, run)
        db.commit()
        try:
            source_record = db.get(DatabaseConnection, plan.source_connection_id)
            destination_record = db.get(DatabaseConnection, plan.destination_connection_id)
            source = _connect(source_record)
            destination = _connect(destination_record)
            record_database_snapshot(db, run, source_record, "source", source)
            record_database_snapshot(db, run, destination_record, "destination", destination)
            db.commit()
            tables = db.query(MigrationPlanTable).filter_by(plan_id=plan.id, selected=True).order_by(
                MigrationPlanTable.source_schema, MigrationPlanTable.source_table
            ).all()

            for table in tables:
                if _cancel_requested(run_id):
                    break
                progress = db.query(MigrationRunTable).filter_by(run_id=run_id, plan_table_id=table.id).one()
                if progress.status == "completed":
                    continue
                mappings = db.query(MigrationColumnMapping).filter_by(plan_table_id=table.id, included=True).order_by(
                    MigrationColumnMapping.source_column
                ).all()
                pairs = [(m.source_column, m.destination_column) for m in mappings if m.destination_column]
                source_pk = (table.source_primary_key or {}).get("constrained_columns") or []
                if not pairs or not source_pk:
                    raise ValueError(f"{table.source_schema}.{table.source_table} requires included mappings and a primary key.")
                mapping = dict(pairs)
                if any(key not in mapping for key in source_pk):
                    raise ValueError(f"All primary-key columns must be included and mapped for {table.source_table}.")
                source_columns = [source_name for source_name, _ in pairs]
                destination_columns = [destination_name for _, destination_name in pairs]
                destination_pk = [mapping[key] for key in source_pk]
                key_meta = [next(c for c in table.source_columns if c.get("name") == key) for key in source_pk]
                progress.status = "running"
                if progress.upper_key is None:
                    upper = _fetch_upper_key(source, table, source_pk)
                    progress.upper_key = _json_key(upper) if upper else []
                    progress.total_rows = source.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(table.source_schema), sql.Identifier(table.source_table)
                    )).fetchone()[0]
                    run.total_rows += progress.total_rows
                    db.commit()
                if not progress.upper_key:
                    progress.status = "completed"
                    run.completed_tables += 1
                    db.commit()
                    continue
                upper_key = _restore_key(progress.upper_key, key_meta)
                last_key = _restore_key(progress.last_key, key_meta) if progress.last_key else None
                unresolved_errors = db.query(MigrationRowError).filter_by(
                    run_table_id=progress.id, resolved_at=None
                ).all()
                retrying_errors = bool(unresolved_errors)
                while True:
                    if _cancel_requested(run_id):
                        break
                    for source_attempt in range(run.max_retries + 1):
                        try:
                            batch = _fetch_batch(
                                source, table, source_pk, source_columns,
                                min(run.batch_size, max(1, 60000 // len(source_columns))),
                                last_key, upper_key,
                            )
                            break
                        except psycopg.OperationalError:
                            progress.retry_count += 1
                            db.commit()
                            if source_attempt >= run.max_retries:
                                raise
                            time.sleep(min(2 ** source_attempt, 15))
                            source.close()
                            source = _connect(source_record)
                    if not batch:
                        break
                    keys = [tuple(row[source_columns.index(name)] for name in source_pk) for row in batch]
                    batch_started = time.monotonic()
                    checkpoint_start = list(last_key) if last_key is not None else None
                    for attempt in range(run.max_retries + 1):
                        try:
                            inserted, updated, skipped, failed, failed_keys = _write_with_isolation(
                                destination, db, run, progress, table, destination_columns,
                                destination_pk, source_pk, batch, keys, run.write_strategy,
                            )
                            break
                        except psycopg.OperationalError:
                            progress.retry_count += 1
                            db.commit()
                            if attempt >= run.max_retries:
                                raise
                            time.sleep(min(2 ** attempt, 15))
                            destination.close()
                            destination = _connect(destination_record)
                    last_key = keys[-1]
                    progress.last_key = _json_key(last_key)
                    if retrying_errors:
                        failed_key_set = {tuple(_json_key(key)) for key in failed_keys}
                        batch_key_set = {tuple(_json_key(key)) for key in keys}
                        for row_error in unresolved_errors:
                            error_key = tuple(row_error.source_key.get(name) for name in source_pk)
                            if error_key not in failed_key_set and error_key in batch_key_set:
                                row_error.resolved_at = datetime.now(UTC)
                    progress.inserted_rows += inserted
                    progress.updated_rows += updated
                    progress.skipped_rows += skipped
                    progress.failed_rows += failed
                    progress.migrated_rows += inserted + updated + skipped
                    run.inserted_rows += inserted
                    run.updated_rows += updated
                    run.skipped_rows += skipped
                    run.failed_rows += failed
                    run.migrated_rows += inserted + updated + skipped
                    run.heartbeat_at = datetime.now(UTC)
                    duration_ms = round((time.monotonic() - batch_started) * 1000, 2)
                    record_committed_batch(
                        db, run, progress, batch, inserted, updated, skipped, failed,
                        checkpoint_start, progress.last_key, duration_ms,
                    )
                    _event(db, run, "batch_committed", progress, rows_read=len(batch), inserted=inserted, updated=updated, skipped=skipped, failed=failed, checkpoint=progress.last_key, duration_ms=duration_ms)
                    db.commit()
                if _cancel_requested(run_id):
                    progress.status = "cancelled"
                    db.commit()
                    break
                progress.status = "partially_failed" if progress.failed_rows else "completed"
                run.completed_tables += 1
                db.commit()
                progress.validation_status = "running"
                db.commit()
                validation_details = _validate_table_detailed(
                    source, destination, table, source_columns,
                    destination_columns, source_pk, destination_pk, run.batch_size,
                )
                mismatch = validation_details["mismatch_rows"]
                progress.mismatch_rows = mismatch
                progress.validation_status = "passed" if mismatch == 0 else "failed"
                run.mismatch_rows += mismatch
                record_table_storage_snapshot(db, run, progress, source, destination)
                _event(
                    db, run, "validation_finished", progress,
                    mismatch_rows=mismatch,
                    validation_status=progress.validation_status,
                    validation=validation_details,
                )
                db.commit()

            cancelled = _cancel_requested(run_id)
            run.validation_status = "failed" if run.mismatch_rows or run.failed_rows else ("passed" if not cancelled else "pending")
            run.status = "cancelled" if cancelled else ("partially_failed" if run.failed_rows or run.mismatch_rows else "completed")
            run.finished_at = datetime.now(UTC)
            run.heartbeat_at = datetime.now(UTC)
            _event(db, run, "run_finished", status=run.status, inserted=run.inserted_rows, updated=run.updated_rows, skipped=run.skipped_rows, failed=run.failed_rows, mismatches=run.mismatch_rows)
            record_database_snapshot(db, run, source_record, "source", source)
            record_database_snapshot(db, run, destination_record, "destination", destination)
            finish_run_metric(db, run)
            db.commit()
        except Exception as exc:
            logger.exception("Migration run %s failed", run_id)
            db.rollback()
            failed_run = db.get(MigrationRun, run_id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.error_message = (
                    f"Migration execution failed ({type(exc).__name__}): "
                    f"{_execution_error_detail(exc)}"
                )[:1200]
                failed_run.finished_at = datetime.now(UTC)
                _event(db, failed_run, "run_failed", error_type=type(exc).__name__)
                finish_run_metric(db, failed_run)
                db.commit()
        finally:
            if source:
                source.close()
            if destination:
                destination.close()


def claim_next_run(worker_id: str | None = None):
    """Claim one queued job atomically; multiple worker processes can share the queue."""
    with SessionLocal() as db:
        run = db.execute(select(MigrationRun).where(MigrationRun.status == "queued")
            .order_by(MigrationRun.created_at).with_for_update(skip_locked=True).limit(1)
        ).scalar_one_or_none()
        if run is None:
            return None
        run.status = "running"
        run.worker_id = worker_id
        run.heartbeat_at = datetime.now(UTC)
        db.add(MigrationRunEvent(run_id=run.id, event_type="worker_claimed", details={"worker_id": worker_id} if worker_id else {}))
        db.commit()
        return run.id


def recover_stale_runs(stale_after_seconds: int = 600):
    """Requeue jobs whose worker disappeared; execution resumes from last_key."""
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    with SessionLocal() as db:
        stale = db.query(MigrationRun).filter(
            MigrationRun.status == "running", MigrationRun.heartbeat_at < cutoff
        ).all()
        for run in stale:
            run.status = "queued"
            run.worker_id = None
            run.error_message = "Worker heartbeat expired; queued for checkpoint recovery."
        db.commit()
        return len(stale)