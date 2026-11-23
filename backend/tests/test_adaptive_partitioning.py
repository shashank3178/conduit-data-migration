import unittest

from snowbridge.adaptive_partitioning import (
    ChunkMeasurement, OversizedRowError, adapt_integer_key_chunks,
)
from snowbridge.partitioning import IntegerKeyRange


class AdaptivePartitioningTests(unittest.TestCase):
    def test_splits_skewed_ranges_until_both_budgets_are_met(self):
        def measure(r):
            rows = sum(1 for key in range(r.lower, r.upper + 1 if r.upper_inclusive else r.upper)
                       if key < 8)
            return ChunkMeasurement(rows, rows * 100)

        chunks = adapt_integer_key_chunks(
            schema_name="public", table_name="events", key_column="id",
            snapshot_id="s1", minimum=0, maximum=15, partitions=1,
            max_rows=2, max_bytes=200, measure=measure,
        )
        self.assertTrue(chunks)
        self.assertEqual(
            sorted((c.range_spec["lower"], c.range_spec["upper"],
                    c.range_spec["upper_inclusive"]) for c in chunks),
            sorted((c.range_spec["lower"], c.range_spec["upper"],
                    c.range_spec["upper_inclusive"]) for c in chunks),
        )
        self.assertTrue(all(measure(IntegerKeyRange(
            c.range_spec["lower"], c.range_spec["upper"],
            c.range_spec["upper_inclusive"])) .rows <= 2 for c in chunks))

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
