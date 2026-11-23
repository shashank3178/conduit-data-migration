import unittest

from snowbridge.postgresql_snapshot import whole_table_chunk


class WholeTableChunkTests(unittest.TestCase):
    def test_creates_deterministic_single_chunk_for_keyless_table(self):
        chunk = whole_table_chunk("public", "events", "snapshot-1")
        self.assertEqual(chunk.chunk_id, "public.events:whole-table")
        self.assertEqual(chunk.range_spec["kind"], "whole_table")
        self.assertEqual(chunk.range_spec["restart_granularity"], "table")
        self.assertEqual(chunk.predicate, "TRUE")

    def test_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            whole_table_chunk("public", "events", "snapshot-1", max_bytes=0)


if __name__ == "__main__":
    unittest.main()
