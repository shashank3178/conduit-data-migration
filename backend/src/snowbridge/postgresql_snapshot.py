"""PostgreSQL snapshot chunk planning and typed range readers."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from snowbridge.adapters.postgresql import (
    PostgresAdapter,
    integer_key_bounds,
    iter_integer_key_chunk_rows,
)
from snowbridge.contracts import ChunkSpec, SnapshotHandle
from snowbridge.partitioning import build_integer_key_chunks
from snowbridge.snapshot import ExportedSnapshot


def integer_key_chunk_factory(
    adapter: PostgresAdapter,
    schema_name: str,
    table_name: str,
    key_column: str,
    *,
    partitions: int = 4,
    max_rows: int = 100_000,
    max_bytes: int = 64 * 1024 * 1024,
) -> Callable[[SnapshotHandle], tuple[ChunkSpec, ...]]:
    """Create a chunk factory whose bounds are read inside the run snapshot."""
    if partitions <= 0 or max_rows <= 0 or max_bytes <= 0:
        raise ValueError("partition, row and byte limits must be positive")

    def factory(snapshot: SnapshotHandle) -> tuple[ChunkSpec, ...]:
        with adapter.connect() as planning_connection:
            ExportedSnapshot(adapter, handle=snapshot).import_into(planning_connection)
            bounds = integer_key_bounds(
                planning_connection, schema_name, table_name, key_column
            )
        if bounds is None:
            return ()
        return build_integer_key_chunks(
            schema_name=schema_name,
            table_name=table_name,
            key_column=key_column,
            snapshot_id=snapshot.snapshot_id,
            minimum=bounds[0],
            maximum=bounds[1],
            partitions=partitions,
            max_rows=max_rows,
            max_bytes=max_bytes,
        )

    return factory


def iter_integer_chunk_rows(
    conn: Any, chunk: ChunkSpec, *, page_size: int = 10_000,
) -> Iterator[tuple[Any, ...]]:
    """Read a planned integer chunk; no SQL fragments are accepted from callers."""
    spec = chunk.range_spec
    if spec.get("kind") != "integer":
        raise ValueError(f"chunk {chunk.chunk_id} is not an integer-key range")
    key_column = spec.get("key_column")
    lower = spec.get("lower")
    upper = spec.get("upper")
    upper_inclusive = spec.get("upper_inclusive")
    if not isinstance(key_column, str) or not key_column:
        raise ValueError("integer chunk has no key column")
    if isinstance(lower, bool) or not isinstance(lower, int):
        raise ValueError("integer chunk has an invalid lower bound")
    if isinstance(upper, bool) or not isinstance(upper, int):
        raise ValueError("integer chunk has an invalid upper bound")
    if not isinstance(upper_inclusive, bool):
        raise ValueError("integer chunk has an invalid upper-bound mode")
    yield from iter_integer_key_chunk_rows(
        conn,
        chunk.schema_name,
        chunk.table_name,
        key_column,
        lower,
        upper,
        upper_inclusive=upper_inclusive,
        page_size=page_size,
    )
