import unittest

from snowbridge.partitioning import (
    IntegerKeyRange,
    build_integer_key_chunks,
    plan_integer_key_ranges,
)


class IntegerKeyRangeTests(unittest.TestCase):
    def test_partitions_are_gap_free_and_cover_negative_to_positive_bounds(self):
        ranges = plan_integer_key_ranges(-7, 8, 4)
        self.assertEqual(ranges, (
            IntegerKeyRange(-7, -3),
            IntegerKeyRange(-3, 1),
            IntegerKeyRange(1, 5),
            IntegerKeyRange(5, 8, upper_inclusive=True),
        ))

    def test_single_value_produces_one_inclusive_range(self):
        self.assertEqual(
            plan_integer_key_ranges(42, 42, 16),
            (IntegerKeyRange(42, 42, upper_inclusive=True),),
        )

    def test_partition_count_is_capped_by_integer_keyspace(self):
        self.assertEqual(len(plan_integer_key_ranges(3, 5, 100)), 3)

    def test_invalid_bounds_and_partition_count_are_rejected(self):
        for args in ((5, 4, 2), (1, 2, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                plan_integer_key_ranges(*args)
        with self.assertRaises(TypeError):
            plan_integer_key_ranges(1.5, 4, 2)

    def test_chunk_specs_have_deterministic_ids_and_bound_parameters(self):
        chunks = build_integer_key_chunks(
            schema_name="public",
            table_name="orders",
            key_column='order"id',
            snapshot_id="snapshot-1",
            minimum=1,
            maximum=10,
            partitions=2,
            max_rows=500,
            max_bytes=4096,
        )
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunk_id, 'public.orders:order"id:000000')
        self.assertEqual(chunks[0].predicate, '"order""id" >= %s AND "order""id" < %s')
        self.assertEqual(chunks[0].parameters, (1, 6))
        self.assertEqual(chunks[1].parameters, (6, 10))
        self.assertTrue(chunks[1].predicate.endswith("<= %s"))
        self.assertEqual(chunks[0].max_rows, 500)
        self.assertEqual(chunks[0].max_bytes, 4096)
        self.assertEqual(chunks[0].range_spec, {
            "kind": "integer", "key_column": 'order"id',
            "lower": 1, "upper": 6, "upper_inclusive": False,
        })


if __name__ == "__main__":
    unittest.main()
