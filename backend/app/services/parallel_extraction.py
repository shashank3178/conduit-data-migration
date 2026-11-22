"""Bounded, independent-connection extraction for integer primary keys."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import psycopg
from psycopg import sql


def extract_integer_key_ranges(
    connect: Callable[[], psycopg.Connection],
    schema: str,
    table: str,
    columns: list[str],
    primary_key: str,
    consume_batch: Callable[[int, list[tuple]], None],
    *,
    workers: int = 4,
    batch_size: int = 2000,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Read disjoint integer-PK ranges concurrently with bounded batch memory.

    Each worker owns its source connection and server-side cursor. The consumer
    is invoked concurrently and must be thread-safe (normally one destination
    connection/transaction per worker). Memory is bounded by workers × batch.
    """
    if not 1 <= workers <= 8:
        raise ValueError("Extraction workers must be between 1 and 8.")
    if not 100 <= batch_size <= 20000:
        raise ValueError("Extraction batch size must be between 100 and 20000.")
    if primary_key not in columns:
        raise ValueError("The partition key must be included in extracted columns.")

    with connect() as metadata_connection:
        bounds = metadata_connection.execute(
            sql.SQL("SELECT MIN({}), MAX({}) FROM {}.{}").format(
                sql.Identifier(primary_key), sql.Identifier(primary_key),
                sql.Identifier(schema), sql.Identifier(table),
            )
        ).fetchone()
    if not bounds or bounds[0] is None:
        return {"rows_fetched": 0, "batches": 0, "partitions": 0}

    lower, upper = bounds
    if isinstance(lower, bool) or not isinstance(lower, int) or not isinstance(upper, int):
        raise ValueError(
            "Parallel range extraction currently requires a single integer primary key; "
            "use the sequential keyset extractor for UUID, composite, or non-integer keys."
        )

    total_keys = upper - lower + 1
    partition_count = min(workers, total_keys)
    ranges = [
        (lower + total_keys * index // partition_count,
         lower + total_keys * (index + 1) // partition_count)
        for index in range(partition_count)
    ]
    fetched = 0
    batches = 0
    lock = threading.Lock()

    def read_partition(partition_id: int, start: int, stop: int) -> tuple[int, int]:
        if cancelled and cancelled():
            return 0, 0
        connection = connect()
        local_rows = 0
        local_batches = 0
        try:
            query = sql.SQL("SELECT {} FROM {}.{} WHERE {} >= %s AND {} < %s ORDER BY {}").format(
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.Identifier(schema), sql.Identifier(table),
                sql.Identifier(primary_key), sql.Identifier(primary_key),
                sql.Identifier(primary_key),
            )
            with connection.cursor(name=f"conduit_extract_{uuid.uuid4().hex[:12]}") as cursor:
                cursor.execute(query, (start, stop))
                while not (cancelled and cancelled()):
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    consume_batch(partition_id, rows)
                    local_rows += len(rows)
                    local_batches += 1
        finally:
            connection.commit()
            connection.close()
        return local_rows, local_batches

    with ThreadPoolExecutor(max_workers=partition_count, thread_name_prefix="conduit-extract") as pool:
        futures = [
            pool.submit(read_partition, index, start, stop)
            for index, (start, stop) in enumerate(ranges)
        ]
        for future in as_completed(futures):
            rows, batch_count = future.result()
            with lock:
                fetched += rows
                batches += batch_count

    return {
        "rows_fetched": fetched,
        "batches": batches,
        "partitions": partition_count,
        "workers": partition_count,
    }
