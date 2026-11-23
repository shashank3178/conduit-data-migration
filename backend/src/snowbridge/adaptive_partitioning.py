"""Adaptive integer-key chunk subdivision with measured row/byte budgets."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from snowbridge.contracts import ChunkSpec
from snowbridge.partitioning import IntegerKeyRange, build_integer_key_chunks


@dataclass(frozen=True, slots=True)
class ChunkMeasurement:
    rows: int
    estimated_bytes: int

    def __post_init__(self) -> None:
        if self.rows < 0 or self.estimated_bytes < 0:
            raise ValueError("chunk measurements cannot be negative")


class OversizedRowError(ValueError):
    """One indivisible integer-key row exceeds the configured byte budget."""


def adapt_integer_key_chunks(
    *, schema_name: str, table_name: str, key_column: str, snapshot_id: str,
    minimum: int, maximum: int, partitions: int, max_rows: int, max_bytes: int,
    measure: Callable[[IntegerKeyRange], ChunkMeasurement], max_depth: int = 64,
) -> tuple[ChunkSpec, ...]:
    """Recursively bisect ranges until measured row and byte budgets are met.

    The measure callback must use the same imported MVCC snapshot as readers.
    Estimated bytes are based on pg_column_size(row), not wire-byte guarantees.
    """
    if max_rows <= 0 or max_bytes <= 0 or max_depth <= 0:
        raise ValueError("row, byte and depth limits must be positive")
    initial = build_integer_key_chunks(
        schema_name=schema_name, table_name=table_name, key_column=key_column,
        snapshot_id=snapshot_id, minimum=minimum, maximum=maximum,
        partitions=partitions, max_rows=max_rows, max_bytes=max_bytes,
    )
    accepted: list[ChunkSpec] = []

    def visit(bounds: IntegerKeyRange, depth: int, path: str) -> None:
        measured = measure(bounds)
        if measured.rows <= max_rows and measured.estimated_bytes <= max_bytes:
            accepted.append(_make_chunk(
                schema_name, table_name, key_column, snapshot_id, bounds,
                max_rows, max_bytes, path,
            ))
            return
        last_value = bounds.upper if bounds.upper_inclusive else bounds.upper - 1
        if bounds.lower >= last_value:
            raise OversizedRowError(
                f"{schema_name}.{table_name} key {bounds.lower} contains "
                f"{measured.rows} row(s) / {measured.estimated_bytes} bytes; "
                f"limits are {max_rows} rows / {max_bytes} bytes. "
                "Increase the byte budget or use a LOB-aware transfer strategy."
            )
        if depth >= max_depth:
            raise ValueError(
                f"adaptive chunk subdivision reached max_depth={max_depth} "
                f"for {schema_name}.{table_name} range "
                f"[{bounds.lower}, {bounds.upper}]"
            )
        midpoint = bounds.lower + (last_value - bounds.lower) // 2
        left = IntegerKeyRange(bounds.lower, midpoint, upper_inclusive=True)
        visit(left, depth + 1, path + "0")
        right_lower = midpoint + 1
        if right_lower <= last_value:
            visit(IntegerKeyRange(right_lower, bounds.upper,
                                  bounds.upper_inclusive), depth + 1, path + "1")

    for chunk in initial:
        spec = chunk.range_spec
        visit(IntegerKeyRange(int(spec["lower"]), int(spec["upper"]),
                              bool(spec["upper_inclusive"])),
              0, chunk.chunk_id.rsplit(":", 1)[-1])
    return tuple(accepted)


def _make_chunk(schema_name: str, table_name: str, key_column: str,
                snapshot_id: str, bounds: IntegerKeyRange, max_rows: int,
                max_bytes: int, path: str) -> ChunkSpec:
    quoted = '"' + key_column.replace('"', '""') + '"'
    op = "<=" if bounds.upper_inclusive else "<"
    return ChunkSpec(
        chunk_id=f"{schema_name}.{table_name}:{key_column}:{path}",
        schema_name=schema_name, table_name=table_name, snapshot_id=snapshot_id,
        predicate=f"{quoted} >= %s AND {quoted} {op} %s",
        parameters=(bounds.lower, bounds.upper), max_rows=max_rows,
        max_bytes=max_bytes,
        range_spec={"kind": "integer", "key_column": key_column,
                    "lower": bounds.lower, "upper": bounds.upper,
                    "upper_inclusive": bounds.upper_inclusive},
    )
