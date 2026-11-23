import unittest

from snowbridge.adaptive_partitioning import (
    ChunkMeasurement, OversizedRowError, adapt_integer_key_chunks,
)
from snowbridge.partitioning import IntegerKeyRange


class AdaptivePartitioningTests(unittest.TestCase):
    def test_splits_skewed_ranges_without_gaps_or_overlaps(self):
        keys = {0, 1, 2, 3, 4, 5, 6, 7, 8, 15}

        def measure(bounds):
            end = bounds.upper if bounds.upper_inclusive else bounds.upper - 1
            rows = sum(bounds.lower <= key <= end for key in keys)
            return ChunkMeasurement(rows, rows * 100)

        chunks = adapt_integer_key_chunks(
            schema_name="public", table_name="events", key_column="id",
            snapshot_id="s1", minimum=0, maximum=15, partitions=1,
            max_rows=2, max_bytes=200, measure=measure,
        )
        migrated = []
        for chunk in chunks:
            spec = chunk.range_spec
            end = spec["upper"] if spec["upper_inclusive"] else spec["upper"] - 1
            migrated.extend(k for k in keys if spec["lower"] <= k <= end)
            self.assertLessEqual(measure(IntegerKeyRange(
                spec["lower"], spec["upper"], spec["upper_inclusive"]
            )).rows, 2)
        self.assertEqual(sorted(migrated), sorted(keys))
        self.assertEqual(len(migrated), len(set(migrated)))

    def test_single_key_over_byte_budget_has_actionable_error(self):
        with self.assertRaisesRegex(OversizedRowError, "LOB-aware"):
            adapt_integer_key_chunks(
                schema_name="public", table_name="payloads", key_column="id",
                snapshot_id="s1", minimum=1, maximum=1, partitions=1,
                max_rows=10, max_bytes=10,
                measure=lambda _: ChunkMeasurement(1, 100),
            )

    def test_measurement_rejects_negative_values(self):
        with self.assertRaises(ValueError):
            ChunkMeasurement(-1, 10)


if __name__ == "__main__":
    unittest.main()
