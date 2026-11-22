"""High-throughput PostgreSQL COPY-to-staging writer.

The caller gets one atomic transaction per batch: staging creation, COPY, and
merge commit together. Checkpoints must only be persisted after this function
returns successfully.
"""
from __future__ import annotations

import uuid

import psycopg
from psycopg import sql
from psycopg.types.json import Json, Jsonb


def _adapt_row(row, columns, column_types):
    if len(row) != len(columns):
        raise ValueError(
            f"COPY row has {len(row)} values for {len(columns)} destination columns."
        )
    values = []
    for column, value in zip(columns, row, strict=True):
        kind = column_types.get(column, "").lower()
        if isinstance(value, (dict, list)):
            if kind == "json":
                value = Json(value)
            elif kind == "jsonb":
                value = Jsonb(value)
            else:
                raise TypeError(
                    f"Cannot COPY Python {type(value).__name__} into "
                    f"destination column {column!r} ({kind or 'unknown'})."
                )
        values.append(value)
    return values


def copy_stage_and_merge(
    destination: psycopg.Connection,
    table,
    destination_columns: list[str],
    conflict_columns: list[str],
    rows,
    strategy: str,
    destination_column_types: dict[str, str] | None = None,
) -> tuple[int, int, int]:
    """COPY rows into a transaction-local stage, then merge into the target."""
    if strategy not in {"INSERT_ONLY", "UPSERT"}:
        raise ValueError(f"Unsupported write strategy: {strategy}")
    if not rows:
        return 0, 0, 0
    if strategy == "UPSERT" and not conflict_columns:
        raise ValueError("UPSERT requires at least one conflict column.")

    types = destination_column_types or {}
    stage_name = f"conduit_stage_{uuid.uuid4().hex}"
    column_identifiers = sql.SQL(", ").join(map(sql.Identifier, destination_columns))
    target = sql.Identifier(table.destination_schema, table.destination_table)
    stage = sql.Identifier("pg_temp", stage_name)

    with destination.transaction():
        destination.execute(
            sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP")
            .format(sql.Identifier(stage_name), target)
        )
        copy_statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
            stage, column_identifiers
        )
        with destination.cursor().copy(copy_statement) as copy:
            for row in rows:
                copy.write_row(_adapt_row(row, destination_columns, types))

        merge = sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
            target, column_identifiers, column_identifiers, stage
        )
        if strategy == "UPSERT":
            update_columns = [
                name for name in destination_columns if name not in conflict_columns
            ]
            if update_columns:
                assignments = sql.SQL(", ").join(
                    sql.SQL("{} = EXCLUDED.{}").format(
                        sql.Identifier(name), sql.Identifier(name)
                    )
                    for name in update_columns
                )
                changed = sql.SQL(" OR ").join(
                    sql.SQL("{} IS DISTINCT FROM EXCLUDED.{}").format(
                        sql.Identifier(table.destination_table, name),
                        sql.Identifier(name),
                    )
                    for name in update_columns
                )
                merge += sql.SQL(" ON CONFLICT ({}) DO UPDATE SET {} WHERE {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, conflict_columns)),
                    assignments,
                    changed,
                )
            else:
                merge += sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
                    sql.SQL(", ").join(map(sql.Identifier, conflict_columns))
                )
        else:
            merge += sql.SQL(" ON CONFLICT DO NOTHING")

        merge += sql.SQL(" RETURNING (xmax = 0)")
        returned = destination.execute(merge).fetchall()
        inserted = sum(1 for result in returned if result[0])
        updated = len(returned) - inserted if strategy == "UPSERT" else 0
        skipped = len(rows) - len(returned)
        return inserted, updated, skipped
