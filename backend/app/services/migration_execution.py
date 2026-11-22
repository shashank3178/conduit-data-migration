"""Durable keyset-paginated PostgreSQL migration execution."""
import logging
import math
import time
import uuid
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from decimal import Decimal
from uuid import UUID as PyUUID
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

import psycopg
from psycopg import sql
from psycopg.types.json import Json, Jsonb
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
    logical_payload_bytes,
    measure_network_rtt,
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


def _get_destination_column_types(destination, table, destination_columns):
    """
    Retrieve destination PostgreSQL column types once per table.

    This metadata is used to adapt Python values correctly before
    passing them to Psycopg.
    """
    # Own this catalog read in a short transaction. Psycopg starts an
    # implicit transaction for execute(); without this boundary, the first
    # INSERT batch can become a savepoint inside the catalog-read transaction.
    # The metadata checkpoint may then commit while destination rows remain
    # uncommitted until validation, making progress appear ahead of durable data.
    with destination.transaction():
        rows = destination.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND column_name = ANY(%s)
            """,
            (
                table.destination_schema,
                table.destination_table,
                destination_columns,
            ),
        ).fetchall()

    column_types = {
        column_name: data_type.lower()
        for column_name, data_type in rows
    }

    missing_columns = [
        column
        for column in destination_columns
        if column not in column_types
    ]

    if missing_columns:
        raise ValueError(
            f"Destination metadata lookup failed for "
            f"{table.destination_schema}.{table.destination_table}. "
            f"Columns not found: {missing_columns}"
        )

    return column_types


def _adapt_write_values(rows, destination_columns, column_types):
    """
    Adapt Python values to their destination PostgreSQL types.

    JSON dictionaries and arrays are explicitly wrapped using Psycopg's
    JSON adapters. Other values retain their original representation.
    """
    flat_values = []

    for row_index, row in enumerate(rows):
        if len(row) != len(destination_columns):
            raise ValueError(
                f"Batch row {row_index} has {len(row)} values, "
                f"but {len(destination_columns)} destination columns."
            )

        for column, value in zip(
            destination_columns,
            row,
            strict=True,
        ):
            destination_type = column_types.get(column, "").lower()

            if isinstance(value, (dict, list)) and destination_type in {
                "json",
                "jsonb",
            }:
                if destination_type == "json":
                    value = Json(value)
                else:
                    value = Jsonb(value)

            elif isinstance(value, dict):
                raise TypeError(
                    f"Unsupported dictionary value during migration. "
                    f"Destination column: {column}; "
                    f"destination PostgreSQL type: {destination_type}; "
                    f"Python source type: dict. "
                    f"Map this column to a JSON or JSONB destination column."
                )

            flat_values.append(value)

    return flat_values


def _write_batch(
    destination,
    table,
    destination_columns,
    conflict_columns,
    rows,
    strategy,
    destination_column_types=None,
):
    """
    Write a batch to PostgreSQL with destination-aware value adaptation.

    Supports INSERT, UPSERT, JSON and JSONB values.
    """
    if not rows:
        return 0, 0, 0

    width = len(destination_columns)

    destination_column_types = destination_column_types or {}
    flat_values = _adapt_write_values(
        rows,
        destination_columns,
        destination_column_types,
    )

    values_sql = sql.SQL(", ").join(
        sql.SQL("({})").format(
            sql.SQL(", ").join(
                sql.Placeholder() for _ in range(width)
            )
        )
        for _ in rows
    )

    query = sql.SQL(
        "INSERT INTO {}.{} ({}) VALUES {}"
    ).format(
        sql.Identifier(table.destination_schema),
        sql.Identifier(table.destination_table),
        sql.SQL(", ").join(
            map(sql.Identifier, destination_columns)
        ),
        values_sql,
    )

    if strategy == "UPSERT":
        update_columns = [
            name
            for name in destination_columns
            if name not in conflict_columns
        ]

        if update_columns:
            assignments = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(
                    sql.Identifier(name),
                    sql.Identifier(name),
                )
                for name in update_columns
            )

            changed = sql.SQL(" OR ").join(
                sql.SQL(
                    "{}.{} IS DISTINCT FROM EXCLUDED.{}"
                ).format(
                    sql.Identifier(table.destination_table),
                    sql.Identifier(name),
                    sql.Identifier(name),
                )
                for name in update_columns
            )

            query += sql.SQL(
                " ON CONFLICT ({}) DO UPDATE SET {} WHERE {}"
            ).format(
                sql.SQL(", ").join(
                    map(sql.Identifier, conflict_columns)
                ),
                assignments,
                changed,
            )

        else:
            query += sql.SQL(
                " ON CONFLICT ({}) DO NOTHING"
            ).format(
                sql.SQL(", ").join(
                    map(sql.Identifier, conflict_columns)
                )
            )

        query += sql.SQL(" RETURNING (xmax = 0)")

        returned = destination.execute(
            query,
            flat_values,
        ).fetchall()

        inserted = sum(
            1 for row in returned if row[0]
        )

        updated = len(returned) - inserted

        skipped = len(rows) - len(returned)

        return inserted, updated, skipped

    query += sql.SQL(
        " ON CONFLICT DO NOTHING RETURNING 1"
    )

    inserted = len(
        destination.execute(
            query,
            flat_values,
        ).fetchall()
    )

    skipped = len(rows) - inserted

    return inserted, 0, skipped


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


def _write_with_isolation(
    destination,
    db,
    run,
    progress,
    table,
    destination_columns,
    destination_column_types,
    conflict_columns,
    key_columns,
    rows,
    keys,
    strategy,
):
    def write_or_split(batch_rows, batch_keys):
        try:
            with destination.transaction():
                return (*_write_batch(
                    destination,
                    table,
                    destination_columns,
                    conflict_columns,
                    batch_rows,
                    strategy,
                    destination_column_types,
                ), 0, [])
        except psycopg.OperationalError:
            raise
        except psycopg.Error as exc:
            if not _is_row_level_write_error(exc):
                raise
            if len(batch_rows) == 1:
                key = batch_keys[0]
                _record_row_error(
                    db, run, progress, key, key_columns, exc,
                )
                return 0, 0, 0, 1, [key]

            # Split only the rejected portion. A single bad row in a large
            # batch now costs O(log N) failed probes rather than N individual
            # INSERT/savepoint round trips over a remote database connection.
            midpoint = len(batch_rows) // 2
            left = write_or_split(batch_rows[:midpoint], batch_keys[:midpoint])
            right = write_or_split(batch_rows[midpoint:], batch_keys[midpoint:])
            return tuple(left[index] + right[index] for index in range(4)) + (
                left[4] + right[4],
            )

    return write_or_split(rows, keys)
    

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
    if (
        isinstance(source_value, float)
        and isinstance(destination_value, float)
        and math.isnan(source_value)
        and math.isnan(destination_value)
    ):
        return True
    if (
        isinstance(source_value, Decimal)
        and isinstance(destination_value, Decimal)
        and source_value.is_nan()
        and destination_value.is_nan()
    ):
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


def _validation_schema_metadata(connection, schema, table_name, columns):
    """Read mapped PostgreSQL types and the destination session timezone."""
    with connection.transaction():
        rows = connection.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
              AND column_name = ANY(%s)
            """,
            (schema, table_name, columns),
        ).fetchall()
        timezone_name = connection.execute(
            "SELECT current_setting('TimeZone')"
        ).fetchone()[0]
    return {name: kind.lower() for name, kind in rows}, timezone_name


def _timestamp_values_equal(source_value, destination_value,
                            source_type, destination_type, destination_timezone):
    """Compare timestamps using PostgreSQL's destination-session cast semantics."""
    if not isinstance(source_value, datetime) or not isinstance(destination_value, datetime):
        return _validation_values_equal(source_value, destination_value)
    source_tz = "with time zone" in source_type
    destination_tz = "with time zone" in destination_type
    if source_tz and destination_tz:
        return source_value.astimezone(UTC) == destination_value.astimezone(UTC)
    if not source_tz and not destination_tz:
        return source_value == destination_value
    zone = ZoneInfo(destination_timezone)
    if not source_tz and destination_tz:
        # PostgreSQL interprets a naive timestamp inserted into timestamptz
        # using the destination connection's TimeZone setting.
        source_value = source_value.replace(tzinfo=zone)
        return source_value.astimezone(UTC) == destination_value.astimezone(UTC)
    # PostgreSQL converts timestamptz to timestamp without time zone in the
    # destination session timezone, dropping the timezone after conversion.
    return source_value.astimezone(zone).replace(tzinfo=None) == destination_value


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
    # Use connection metadata to distinguish timestamp-with/without-time-zone.
    # This avoids treating equivalent PostgreSQL casts as data corruption while
    # preserving strict comparisons for all other mapped values.
    source_types = {}
    destination_types = {}
    destination_timezone = "UTC"
    try:
        source_types, _ = _validation_schema_metadata(
            source, table.source_schema, table.source_table, source_columns
        )
        destination_types, destination_timezone = _validation_schema_metadata(
            destination, table.destination_schema, table.destination_table,
            destination_columns,
        )
    except (AttributeError, TypeError):
        # Lightweight test doubles may expose cursors only. Real psycopg
        # connections always provide transaction() and execute().
        source_types, destination_types = {}, {}
    details = {
        "source_rows": 0,
        "destination_rows": 0,
        "missing_in_destination": 0,
        "extra_in_destination": 0,
        "changed_rows": 0,
        "matched_rows": 0,
        "mismatch_rows": 0,
        "samples": [],
        "sample_limit": sample_limit,
        "comparison": "primary-key ordered streaming comparison with PostgreSQL type-aware timestamp semantics",
        "timestamp_timezone": destination_timezone,
        "timestamp_columns_normalized": [],
    }

    def add_sample(reason, key, columns=None, type_differences=None, value_differences=None):
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
        if value_differences:
            sample["timestamp_value_differences"] = value_differences
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
                details["source_rows"] += 1
                details["missing_in_destination"] += 1
                add_sample("MISSING_IN_DESTINATION", source_key)
                source_row = next(source_rows, None)
            elif destination_before_source:
                details["destination_rows"] += 1
                details["extra_in_destination"] += 1
                add_sample("EXTRA_IN_DESTINATION", destination_key)
                destination_row = next(destination_rows, None)
            else:
                details["source_rows"] += 1
                details["destination_rows"] += 1
                details["matched_rows"] += 1
                different_columns = []
                type_differences = {}
                timestamp_value_differences = {}
                for index, (source_value, destination_value) in enumerate(
                    zip(source_row, destination_row, strict=True)
                ):
                    column_name = source_columns[index]
                    destination_column = destination_columns[index]
                    source_type = source_types.get(column_name, "")
                    destination_type = destination_types.get(destination_column, "")
                    is_timestamp_pair = (
                        source_type.startswith("timestamp")
                        and destination_type.startswith("timestamp")
                    )
                    equal = (
                        _timestamp_values_equal(
                            source_value, destination_value, source_type,
                            destination_type, destination_timezone,
                        )
                        if is_timestamp_pair
                        else _validation_values_equal(source_value, destination_value)
                    )
                    if is_timestamp_pair and column_name not in details["timestamp_columns_normalized"]:
                        details["timestamp_columns_normalized"].append(column_name)
                    if not equal:
                        different_columns.append(column_name)
                        if is_timestamp_pair:
                            timestamp_value_differences[column_name] = {
                                "source": source_value.isoformat() if isinstance(source_value, datetime) else repr(source_value),
                                "destination": destination_value.isoformat() if isinstance(destination_value, datetime) else repr(destination_value),
                                "source_postgres_type": source_type,
                                "destination_postgres_type": destination_type,
                                "destination_timezone": destination_timezone,
                            }
                        if type(source_value) is not type(destination_value):
                            type_differences[column_name] = {
                                "source": type(source_value).__name__,
                                "destination": type(destination_value).__name__,
                                "source_postgres_type": source_type or "unknown",
                                "destination_postgres_type": destination_type or "unknown",
                            }
                if different_columns:
                    details["changed_rows"] += 1
                    reason = "TYPE_MISMATCH" if type_differences else "COLUMN_VALUE_MISMATCH"
                    add_sample(
                        reason, source_key, different_columns,
                        type_differences or None,
                        timestamp_value_differences or None,
                    )
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

    if details["changed_rows"] > details["matched_rows"]:
        raise RuntimeError(
            "Validation accounting invariant failed: changed row count exceeds "
            "the number of rows matched by primary key."
        )
    details["mismatch_rows"] = (
        details["missing_in_destination"]
        + details["extra_in_destination"]
        + details["changed_rows"]
    )
    details["exact_match_rows"] = max(
        0, details["matched_rows"] - details["changed_rows"]
    )
    details["row_count_delta"] = (
        details["destination_rows"] - details["source_rows"]
    )
    comparison_denominator = max(
        details["source_rows"], details["destination_rows"]
    )
    details["data_consistency_percent"] = (
        round(details["exact_match_rows"] / comparison_denominator * 100, 4)
        if comparison_denominator else 100.0
    )
    details["validation_checks"] = {
        "row_count_match": details["row_count_delta"] == 0,
        "primary_key_set_match": (
            details["missing_in_destination"] == 0
            and details["extra_in_destination"] == 0
        ),
        "mapped_column_values_match": details["changed_rows"] == 0,
        "all_rows_exact_match": details["mismatch_rows"] == 0,
    }
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
            network_rtt = {
                "source": measure_network_rtt(source),
                "destination": measure_network_rtt(destination),
            }
            run_metric = ensure_run_metric(db, run)
            run_metric.source_network_rtt_ms = network_rtt["source"]
            run_metric.destination_network_rtt_ms = network_rtt["destination"]
            db.commit()
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
                if (
                    progress.status in {"completed", "partially_failed"}
                    and progress.validation_status in {"passed", "failed"}
                ):
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
                source_columns = [
                    source_name for source_name, _ in pairs
                ]

                destination_columns = [
                    destination_name for _, destination_name in pairs
                ]

                destination_pk = [
                    mapping[key] for key in source_pk
                ]

                key_meta = [
                    next(
                        c for c in table.source_columns
                        if c.get("name") == key
                    )
                    for key in source_pk
                ]

                # Retrieve destination column types once per table.
                destination_column_types = _get_destination_column_types(
                    destination,
                    table,
                    destination_columns,
                )
                progress.status = "running"
                if progress.upper_key is None:
                    upper = _fetch_upper_key(source, table, source_pk)
                    progress.upper_key = _json_key(upper) if upper else []
                    progress.total_rows = source.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(table.source_schema), sql.Identifier(table.source_table)
                    )).fetchone()[0]
                    run.total_rows += progress.total_rows
                    db.commit()
                upper_key = (
                    _restore_key(progress.upper_key, key_meta)
                    if progress.upper_key
                    else None
                )
                last_key = _restore_key(progress.last_key, key_meta) if progress.last_key else None
                unresolved_errors = db.query(MigrationRowError).filter_by(
                    run_table_id=progress.id, resolved_at=None
                ).all()
                retrying_errors = bool(unresolved_errors)
                while upper_key is not None:
                    if _cancel_requested(run_id):
                        break
                    batch_started = time.monotonic()
                    fetch_started = time.monotonic()
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
                    fetch_duration_ms = round((time.monotonic() - fetch_started) * 1000, 2)
                    if not batch:
                        break
                    keys = [tuple(row[source_columns.index(name)] for name in source_pk) for row in batch]
                    write_started = time.monotonic()
                    checkpoint_start = list(last_key) if last_key is not None else None
                    for attempt in range(run.max_retries + 1):
                        try:
                            inserted, updated, skipped, failed, failed_keys = _write_with_isolation(
                            destination,
                            db,
                            run,
                            progress,
                            table,
                            destination_columns,
                            destination_column_types,
                            destination_pk,
                            source_pk,
                            batch,
                            keys,
                            run.write_strategy,
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
                    destination_write_duration_ms = round((time.monotonic() - write_started) * 1000, 2)
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
                    batch_logical_bytes = logical_payload_bytes(batch)
                    record_committed_batch(
                        db, run, progress, batch, inserted, updated, skipped, failed,
                        checkpoint_start, progress.last_key, duration_ms,
                        source_fetch_duration_ms=fetch_duration_ms,
                        destination_write_duration_ms=destination_write_duration_ms,
                        network_rtt_ms=network_rtt,
                        logical_payload_size=batch_logical_bytes,
                    )
                    _event(db, run, "batch_committed", progress, rows_read=len(batch), inserted=inserted, updated=updated, skipped=skipped, failed=failed, checkpoint=progress.last_key, logical_bytes=batch_logical_bytes, duration_ms=duration_ms, source_fetch_duration_ms=fetch_duration_ms, destination_write_duration_ms=destination_write_duration_ms, source_network_rtt_ms=network_rtt["source"], destination_network_rtt_ms=network_rtt["destination"])
                    db.commit()
                if _cancel_requested(run_id):
                    progress.status = "cancelled"
                    db.commit()
                    break
                was_already_completed = progress.status in {"completed", "partially_failed"}
                progress.status = "partially_failed" if progress.failed_rows else "completed"
                if not was_already_completed:
                    run.completed_tables += 1
                db.commit()
                progress.validation_status = "running"
                db.commit()
                try:
                    validation_details = _validate_table_detailed(
                        source, destination, table, source_columns,
                        destination_columns, source_pk, destination_pk, run.batch_size,
                    )
                except Exception as exc:
                    progress.validation_status = "failed"
                    progress.error_message = (
                        f"Validation execution failed ({type(exc).__name__}): "
                        f"{_execution_error_detail(exc)}"
                    )[:1200]
                    run.validation_status = "failed"
                    _event(
                        db, run, "validation_error", progress,
                        error_type=type(exc).__name__,
                        error_message=progress.error_message,
                    )
                    db.commit()
                    raise
                mismatch = validation_details["mismatch_rows"]
                progress.mismatch_rows = mismatch
                progress.validation_status = "passed" if mismatch == 0 else "failed"
                if mismatch:
                    samples = validation_details["samples"][:3]
                    sample_summary = "; ".join(
                        f"{sample['reason']} key={sample.get('primary_key')} "
                        f"columns={sample.get('different_columns', [])}"
                        for sample in samples
                    )
                    progress.error_message = (
                        f"Validation failed: {mismatch} mismatched rows; "
                        f"missing in destination={validation_details['missing_in_destination']}, "
                        f"extra in destination={validation_details['extra_in_destination']}, "
                        f"changed rows={validation_details['changed_rows']}. "
                        f"Sample mismatches: {sample_summary or 'No sample available.'}"
                    )[:1200]
                elif progress.failed_rows:
                    progress.error_message = (
                        f"Validation passed for the compared rows, but "
                        f"{progress.failed_rows} row(s) failed during destination writes. "
                        "Inspect the row-level error records for source keys and PostgreSQL causes."
                    )[:1200]
                else:
                    progress.error_message = None
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