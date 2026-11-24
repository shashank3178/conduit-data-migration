"""High-throughput PostgreSQL COPY staging writer.

The staging relation is created once per destination connection/table and reused
across batches. Callers must wrap this function in a destination transaction so
COPY, merge, and checkpoint bookkeeping retain the existing atomicity boundary.
"""
from __future__ import annotations

import hashlib
import os

from psycopg import sql


def write_copy_batch(
    destination,
    table,
    destination_columns,
    conflict_columns,
    rows,
    strategy,
    destination_column_types,
    adapt_values,
):
    if not rows:
        return 0, 0, 0

    identity = f"{table.destination_schema}.{table.destination_table}".encode()
    stage_name = "conduit_stage_" + hashlib.sha256(identity).hexdigest()[:16]
    columns_sql = sql.SQL(", ").join(map(sql.Identifier, destination_columns))
    target = sql.SQL("{}.{}").format(
        sql.Identifier(table.destination_schema),
        sql.Identifier(table.destination_table),
    )
    stage = sql.SQL("pg_temp.{}").format(sql.Identifier(stage_name))

    # ON COMMIT PRESERVE ROWS is essential: the temp relation survives each
    # per-batch transaction on this worker's persistent destination connection.
    destination.execute(
        sql.SQL(
            "CREATE TEMP TABLE IF NOT EXISTS {} "
            "(LIKE {} INCLUDING DEFAULTS) ON COMMIT PRESERVE ROWS"
        ).format(sql.Identifier(stage_name), target)
    )
    destination.execute(sql.SQL("TRUNCATE TABLE {}").format(stage))

    flat_values = adapt_values(rows, destination_columns, destination_column_types)
    width = len(destination_columns)
    adapted_rows = (
        tuple(flat_values[offset:offset + width])
        for offset in range(0, len(flat_values), width)
    )
    copy_format = os.getenv("CONDUIT_COPY_FORMAT", "text").strip().lower()
    if copy_format not in {"text", "binary"}:
        copy_format = "text"
    copy_query = sql.SQL("COPY {} ({}) FROM STDIN{}").format(
        stage,
        columns_sql,
        sql.SQL(" (FORMAT BINARY)") if copy_format == "binary" else sql.SQL(""),
    )
    with destination.cursor().copy(copy_query) as copy:
        for row in adapted_rows:
            copy.write_row(row)

    insert = sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
        target, columns_sql, columns_sql, stage
    )
    if strategy == "UPSERT":
        updates = [name for name in destination_columns if name not in conflict_columns]
        if updates:
            assignments = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(name), sql.Identifier(name))
                for name in updates
            )
            changed = sql.SQL(" OR ").join(
                sql.SQL("{}.{} IS DISTINCT FROM EXCLUDED.{}").format(
                    sql.Identifier(table.destination_table),
                    sql.Identifier(name),
                    sql.Identifier(name),
                )
                for name in updates
            )
            insert += sql.SQL(" ON CONFLICT ({}) DO UPDATE SET {} WHERE {}").format(
                sql.SQL(", ").join(map(sql.Identifier, conflict_columns)),
                assignments,
                changed,
            )
        else:
            insert += sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
                sql.SQL(", ").join(map(sql.Identifier, conflict_columns))
            )
        insert += sql.SQL(" RETURNING (xmax = 0) AS inserted")
        aggregate = sql.SQL(
            "WITH merged AS ({}) "
            "SELECT count(*) FILTER (WHERE inserted), "
            "count(*) FILTER (WHERE NOT inserted) FROM merged"
        ).format(insert)
        inserted, updated = destination.execute(aggregate).fetchone()
        skipped = len(rows) - inserted - updated
    else:
        insert += sql.SQL(" ON CONFLICT DO NOTHING RETURNING 1")
        aggregate = sql.SQL(
            "WITH merged AS ({}) SELECT count(*) FROM merged"
        ).format(insert)
        inserted = destination.execute(aggregate).fetchone()[0]
        updated = 0
        skipped = len(rows) - inserted

    # The next batch truncates this connection-local staging table before use.
    # Avoid an extra TRUNCATE round trip after every merge.
    return inserted, updated, skipped
