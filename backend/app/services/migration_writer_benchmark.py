"""Benchmark VALUES versus COPY writers against disposable destination tables.

Run from backend with SOURCE_DATABASE_URL and DESTINATION_DATABASE_URL set.
The destination template table is never modified; each run uses a temporary
benchmark schema and drops it after recording timings.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from types import SimpleNamespace

import psycopg
from psycopg import sql

from app.services.migration_execution import _write_batch
from app.services.migration_metrics_service import logical_payload_bytes


def _columns(connection, schema: str, table: str) -> list[str]:
    with connection.transaction():
        rows = connection.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
              AND is_generated = 'NEVER'
            ORDER BY ordinal_position
            """,
            (schema, table),
        ).fetchall()
    return [row[0] for row in rows]


def benchmark_writer(
    source_dsn: str,
    destination_dsn: str,
    source_schema: str,
    source_table: str,
    destination_schema: str,
    destination_table: str,
    batch_size: int,
    writer: str,
) -> dict:
    if writer not in {"values", "copy"}:
        raise ValueError("writer must be 'values' or 'copy'")
    source = psycopg.connect(source_dsn)
    destination = psycopg.connect(destination_dsn)
    benchmark_schema = f"conduit_bench_{uuid.uuid4().hex[:12]}"
    try:
        source_columns = _columns(source, source_schema, source_table)
        destination_columns = _columns(destination, destination_schema, destination_table)
        columns = [name for name in source_columns if name in destination_columns]
        if not columns:
            raise ValueError("Source and destination template have no identically named columns.")
        if len(columns) != len(source_columns):
            raise ValueError(
                "Benchmark requires every source column to have an identically named "
                "destination column; use the real migration plan for mapped schemas."
            )
        table = SimpleNamespace(
            destination_schema=benchmark_schema,
            destination_table=source_table,
        )
        with destination.transaction():
            destination.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(benchmark_schema)))
            destination.execute(
                sql.SQL("CREATE TABLE {}.{} (LIKE {}.{} INCLUDING ALL)").format(
                    sql.Identifier(benchmark_schema), sql.Identifier(source_table),
                    sql.Identifier(destination_schema), sql.Identifier(destination_table),
                )
            )
        with destination.transaction():
            type_rows = destination.execute(
                """
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (benchmark_schema, source_table),
            ).fetchall()
        column_types = {name: kind.lower() for name, kind in type_rows}
        select_query = sql.SQL("SELECT {} FROM {}.{}").format(
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.Identifier(source_schema), sql.Identifier(source_table),
        )
        source_fetch_seconds = 0.0
        destination_write_seconds = 0.0
        elapsed_started = time.monotonic()
        rows_fetched = 0
        batches = 0
        logical_bytes = 0
        os.environ["CONDUIT_WRITE_ENGINE"] = writer
        with source.cursor(name=f"conduit_bench_{uuid.uuid4().hex[:12]}") as cursor:
            cursor.execute(select_query)
            while True:
                fetch_started = time.monotonic()
                rows = cursor.fetchmany(batch_size)
                source_fetch_seconds += time.monotonic() - fetch_started
                if not rows:
                    break
                write_started = time.monotonic()
                with destination.transaction():
                    _write_batch(
                        destination, table, columns, [], rows, "INSERT_ONLY",
                        column_types,
                    )
                destination_write_seconds += time.monotonic() - write_started
                rows_fetched += len(rows)
                batches += 1
                logical_bytes += logical_payload_bytes(rows)
        source.commit()
        elapsed_seconds = time.monotonic() - elapsed_started
        with destination.transaction():
            destination_rows = destination.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(benchmark_schema), sql.Identifier(source_table)
                )
            ).fetchone()[0]
        return {
            "writer": writer,
            "rows_fetched": rows_fetched,
            "destination_rows": destination_rows,
            "batches": batches,
            "logical_bytes": logical_bytes,
            "batch_size": batch_size,
            "source_fetch_seconds": round(source_fetch_seconds, 3),
            "destination_write_seconds": round(destination_write_seconds, 3),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "end_to_end_mib_per_second": round(
                logical_bytes / 1048576 / elapsed_seconds, 3
            ) if elapsed_seconds else 0,
            "destination_write_mib_per_second": round(
                logical_bytes / 1048576 / destination_write_seconds, 3
            ) if destination_write_seconds else 0,
            "count_check_passed": destination_rows == rows_fetched,
        }
    finally:
        os.environ.pop("CONDUIT_WRITE_ENGINE", None)
        try:
            with destination.transaction():
                destination.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(benchmark_schema)
                    )
                )
        finally:
            source.close()
            destination.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compare PostgreSQL VALUES and COPY writers.")
    parser.add_argument("--source-schema", required=True)
    parser.add_argument("--source-table", required=True)
    parser.add_argument("--destination-schema", required=True)
    parser.add_argument("--destination-table", required=True)
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    source_dsn = os.environ["SOURCE_DATABASE_URL"]
    destination_dsn = os.environ["DESTINATION_DATABASE_URL"]
    results = [
        benchmark_writer(
            source_dsn, destination_dsn, args.source_schema, args.source_table,
            args.destination_schema, args.destination_table, args.batch_size, writer,
        )
        for writer in ("values", "copy")
    ]
    print(json.dumps(results, indent=2))
