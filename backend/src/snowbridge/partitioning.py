"""Deterministic, non-overlapping integer-key range planning.

The planner deliberately handles only a single integral key. Composite, UUID,
text, and non-orderable keys remain a single keyset stream until an adapter
provides a statistically sound boundary strategy; it never falls back to
OFFSET pagination.
"""
from __future__ import annotations

from dataclasses import dataclass

from snowbridge.contracts import ChunkSpec


@dataclass(frozen=True, slots=True)
class IntegerKeyRange:
    lower: int
    upper: int
    upper_inclusive: bool = False

    def __post_init__(self) -> None:
        if self.upper < self.lower:
            raise ValueError("range upper bound must be >= lower bound")
        if self.upper == self.lower and not self.upper_inclusive:
            raise ValueError("an empty half-open key range is not valid")


def plan_integer_key_ranges(
    minimum: int,
    maximum: int,
    partitions: int,
) -> tuple[IntegerKeyRange, ...]:
    """Split [minimum, maximum] into deterministic, gap-free integer ranges.

    Ranges are half-open except for the final range, which includes maximum.
    Sparse keys may yield empty ranges; the reader handles these as zero-row
    chunks. The number of ranges never exceeds the integer key-space width.
    """
    if isinstance(minimum, bool) or isinstance(maximum, bool):
        raise TypeError("boolean values are not valid integer key bounds")
    if not isinstance(minimum, int) or not isinstance(maximum, int):
        raise TypeError("integer range planning requires integral bounds")
    if maximum < minimum:
        raise ValueError("maximum key must be >= minimum key")
    if partitions <= 0:
        raise ValueError("partitions must be positive")

    width = maximum - minimum + 1
    count = min(partitions, width)
    step = (width + count - 1) // count
    ranges: list[IntegerKeyRange] = []
    lower = minimum
    while lower <= maximum:
        upper_exclusive = min(lower + step, maximum + 1)
        final = upper_exclusive == maximum + 1
        ranges.append(IntegerKeyRange(
            lower=lower,
            upper=maximum if final else upper_exclusive,
            upper_inclusive=final,
        ))
        lower = upper_exclusive
    return tuple(ranges)


def build_integer_key_chunks(
    *,
    schema_name: str,
    table_name: str,
    key_column: str,
    snapshot_id: str,
    minimum: int,
    maximum: int,
    partitions: int,
    max_rows: int = 100_000,
    max_bytes: int = 64 * 1024 * 1024,
) -> tuple[ChunkSpec, ...]:
    """Create stable ChunkSpec records with safely quoted key identifiers."""
    if not schema_name or not table_name or not key_column or not snapshot_id:
        raise ValueError("schema, table, key column and snapshot id are required")
    if max_rows <= 0 or max_bytes <= 0:
        raise ValueError("chunk row and byte limits must be positive")

    quoted_key = '"' + key_column.replace('"', '""') + '"'
    chunks: list[ChunkSpec] = []
    for index, key_range in enumerate(
        plan_integer_key_ranges(minimum, maximum, partitions)
    ):
        if key_range.upper_inclusive:
            predicate = f"{quoted_key} >= %s AND {quoted_key} <= %s"
        else:
            predicate = f"{quoted_key} >= %s AND {quoted_key} < %s"
        chunks.append(ChunkSpec(
            chunk_id=f"{schema_name}.{table_name}:{key_column}:{index:06d}",
            schema_name=schema_name,
            table_name=table_name,
            snapshot_id=snapshot_id,
            predicate=predicate,
            parameters=(key_range.lower, key_range.upper),
            max_rows=max_rows,
            max_bytes=max_bytes,
        ))
    return tuple(chunks)
