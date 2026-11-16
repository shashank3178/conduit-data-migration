"""Durable keyset-paginated PostgreSQL migration execution."""
import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID as PyUUID

import psycopg
from psycopg import sql
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.connection import DatabaseConnection
from app.models.migration_plan import MigrationColumnMapping, MigrationPlan, MigrationPlanTable
from app.models.migration_run import MigrationRowError, MigrationRun, MigrationRunTable
from app.services.connection_service import decrypt_password


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
        if isinstance(value, (datetime, date)):
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
        elif any(token in kind for token in ("CHAR", "TEXT", "NAME")):
            restored.append(str(value))
        else:
            raise ValueError(f"Unsupported primary-key type for resumable execution: {kind}")
    return tuple(restored)


def _tuple_sql(columns):
    return sql.SQL("({})").format(sql.SQL(", ").join(map(sql.Identifier, columns)))


def _fetch_upper_key(source, table, pk_columns):
    query = sql.SQL("SELECT {} FROM {}.{} ORDER BY {} DESC LIMIT 1").format(
        sql.SQL(", ").join(map(sql.Identifier, pk_columns)),
        sql.Identifier(table.source_schema), sql.Identifier(table.source_table),
        sql.SQL(", ").join(sql.SQL("{} DESC").format(sql.Identifier(name)) for name in pk_columns),
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


def _record_row_error(db, run, progress, key, exc):
    db.add(MigrationRowError(
        run_id=run.id, run_table_id=progress.id,
        source_key={str(index): value for index, value in enumerate(_json_key(key))},
        error_type=type(exc).__name__,
        error_message=f"Destination row write failed ({type(exc).__name__}).",
        attempts=progress.retry_count + 1,
    ))


def _write_with_isolation(destination, db, run, progress, table, destination_columns,
                          conflict_columns, rows, keys, strategy):
    try:
        with destination.transaction():
            result = _write_batch(destination, table, destination_columns, conflict_columns, rows, strategy)
        return (*result, 0)
    except psycopg.Error:
        inserted = updated = skipped = failed = 0
        with destination.transaction():
            for row, key in zip(rows, keys, strict=True):
                try:
                    with destination.transaction():
                        outcome = _write_batch(destination, table, destination_columns, conflict_columns, [row], strategy)
                    inserted += outcome[0]
                    updated += outcome[1]
                    skipped += outcome[2]
                except psycopg.Error as exc:
                    failed += 1
                    _record_row_error(db, run, progress, key, exc)
        return inserted, updated, skipped, failed


def _validate_table(source, destination, table, source_columns, destination_columns,
                    source_pk, destination_pk, batch_size):
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
    mismatch = 0
    with source.cursor(name=f"validate_src_{uuid.uuid4().hex[:16]}") as left, destination.cursor(
        name=f"validate_dst_{uuid.uuid4().hex[:16]}"
    ) as right:
        left.execute(source_query)
        right.execute(destination_query)
        while True:
            source_rows = left.fetchmany(batch_size)
            destination_rows = right.fetchmany(batch_size)
            if not source_rows and not destination_rows:
                break
            mismatch += abs(len(source_rows) - len(destination_rows))
            mismatch += sum(1 for a, b in zip(source_rows, destination_rows) if tuple(a) != tuple(b))
    return mismatch


def execute_run(run_id: uuid.UUID) -> None:
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
        run.started_at = run.started_at or datetime.now(UTC)
        run.heartbeat_at = datetime.now(UTC)
        db.commit()
        try:
            source_record = db.get(DatabaseConnection, plan.source_connection_id)
            destination_record = db.get(DatabaseConnection, plan.destination_connection_id)
            source = _connect(source_record)
            destination = _connect(destination_record)
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
                while True:
                    if _cancel_requested(run_id):
                        break
                    batch = _fetch_batch(source, table, source_pk, source_columns,
                                         min(run.batch_size, max(1, 60000 // len(source_columns))),
                                         last_key, upper_key)
                    if not batch:
                        break
                    keys = [tuple(row[source_columns.index(name)] for name in source_pk) for row in batch]
                    for attempt in range(run.max_retries + 1):
                        try:
                            inserted, updated, skipped, failed = _write_with_isolation(
                                destination, db, run, progress, table, destination_columns,
                                destination_pk, batch, keys, run.write_strategy,
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
                mismatch = _validate_table(source, destination, table, source_columns,
                    destination_columns, source_pk, destination_pk, run.batch_size)
                progress.mismatch_rows = mismatch
                progress.validation_status = "passed" if mismatch == 0 else "failed"
                run.mismatch_rows += mismatch
                db.commit()

            cancelled = _cancel_requested(run_id)
            run.validation_status = "failed" if run.mismatch_rows or run.failed_rows else ("passed" if not cancelled else "pending")
            run.status = "cancelled" if cancelled else ("partially_failed" if run.failed_rows or run.mismatch_rows else "completed")
            run.finished_at = datetime.now(UTC)
            run.heartbeat_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:
            db.rollback()
            failed_run = db.get(MigrationRun, run_id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.error_message = f"Migration execution failed ({type(exc).__name__})."
                failed_run.finished_at = datetime.now(UTC)
                db.commit()
        finally:
            if source:
                source.close()
            if destination:
                destination.close()


def claim_next_run():
    """Claim one queued job atomically; multiple worker processes can share the queue."""
    with SessionLocal() as db:
        run = db.execute(select(MigrationRun).where(MigrationRun.status == "queued")
            .order_by(MigrationRun.created_at).with_for_update(skip_locked=True).limit(1)
        ).scalar_one_or_none()
        if run is None:
            return None
        run.status = "running"
        run.heartbeat_at = datetime.now(UTC)
        db.commit()
        return run.id


def recover_stale_runs(stale_after_seconds: int = 120):
    """Requeue jobs whose worker disappeared; execution resumes from last_key."""
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    with SessionLocal() as db:
        stale = db.query(MigrationRun).filter(
            MigrationRun.status == "running", MigrationRun.heartbeat_at < cutoff
        ).all()
        for run in stale:
            run.status = "queued"
            run.error_message = "Worker heartbeat expired; queued for checkpoint recovery."
        db.commit()
        return len(stale)
