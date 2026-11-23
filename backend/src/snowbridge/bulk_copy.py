"""Byte-bounded PostgreSQL binary COPY transfer between source and target.

This path is intended for PostgreSQL-to-PostgreSQL transfers where the source
and target columns have binary-compatible PostgreSQL types. It avoids
materializing decoded Python rows and moves data in fixed-size byte blocks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from psycopg.copy import LibpqWriter

from snowbridge.adapters.postgresql import _require_driver, sql


@dataclass(frozen=True, slots=True)
class BinaryCopyResult:
    rows: int
    bytes_transferred: int


def copy_binary_integer_range(
    source_conn: Any,
    target_conn: Any,
    *,
    source_schema: str,
    source_table: str,
    target_schema: str,
    target_table: str,
    columns: Sequence[str],
    key_column: str,
    lower_bound: int,
    upper_bound: int,
    upper_inclusive: bool = False,
    block_bytes: int = 1024 * 1024,
) -> BinaryCopyResult:
    """Pipe a bounded source query directly into target COPY using fixed blocks.

    Source and target transactions are owned by the caller. The source
    connection must already have imported the run snapshot. The target table
    must exist and each selected column must have a binary-compatible type.
    The target transaction must be committed only with its idempotency ledger
    record by the higher-level execution protocol.
    """
    _require_driver()
    if not columns:
        raise ValueError("binary COPY requires an explicit column list")
    if not all((source_schema, source_table, target_schema, target_table, key_column)):
        raise ValueError("source/target tables and key column are required")
    if isinstance(lower_bound, bool) or isinstance(upper_bound, bool):
        raise TypeError("integer key bounds cannot be booleans")
    if not isinstance(lower_bound, int) or not isinstance(upper_bound, int):
        raise TypeError("integer key bounds must be integers")
    if upper_bound < lower_bound or (
        upper_bound == lower_bound and not upper_inclusive
    ):
        raise ValueError("invalid integer key range")
    if block_bytes <= 0:
        raise ValueError("block_bytes must be positive")

    selected = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    key = sql.Identifier(key_column)
    source = sql.Identifier(source_schema, source_table)
    target = sql.Identifier(target_schema, target_table)
    comparison = sql.SQL("<=") if upper_inclusive else sql.SQL("<")
    select = sql.SQL(
        "SELECT {columns} FROM {source} "
        "WHERE {key} >= %s AND {key} {comparison} %s ORDER BY {key}"
    ).format(
        columns=selected,
        source=source,
        key=key,
        comparison=comparison,
    )
    copy_out = sql.SQL("COPY ({}) TO STDOUT (FORMAT BINARY)").format(select)
    copy_in = sql.SQL("COPY {} ({}) FROM STDIN (FORMAT BINARY)").format(
        target, selected
    )

    transferred = 0
    with source_conn.cursor() as source_cursor:
        with source_cursor.copy(copy_out, (lower_bound, upper_bound)) as reader:
            with target_conn.cursor() as target_cursor:
                with target_cursor.copy(copy_in) as writer:
                    while True:
                        block = reader.read(size=block_bytes)
                        if not block:
                            break
                        writer.write(block)
                        transferred += len(block)
                rows = writer.rowcount
    if rows < 0:
        raise RuntimeError("PostgreSQL did not report the binary COPY row count")
    return BinaryCopyResult(rows=rows, bytes_transferred=transferred)
