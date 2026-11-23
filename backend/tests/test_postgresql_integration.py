"""Real PostgreSQL adapter tests; enabled by SNOWBRIDGE_TEST_DATABASE_URL."""
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql

from snowbridge.adapters.postgresql import (
    PostgresAdapter, PostgresEndpoint, copy_rows, integer_key_bounds,
    iter_integer_key_chunk_rows,
)
from snowbridge.snapshot import ExportedSnapshot
from snowbridge.bulk_copy import copy_binary_integer_range


DSN = os.getenv("SNOWBRIDGE_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "SNOWBRIDGE_TEST_DATABASE_URL is not configured")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "sb_test_" + uuid4().hex[:12]
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL(
                "CREATE TABLE {}.source_rows (id bigint PRIMARY KEY, value text)"
            ).format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL(
                "INSERT INTO {}.source_rows VALUES (1, %s), (2, %s)"
            ).format(sql.Identifier(self.schema)), ("one", "two"))

    def tearDown(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(self.schema)
            ))

    def test_exported_snapshot_is_consistent_across_worker(self):
        adapter = PostgresAdapter(PostgresEndpoint(DSN))
        with ExportedSnapshot(adapter) as snapshot:
            with adapter.connect() as worker:
                # Import must be the first transaction-level operation on worker.
                from psycopg import sql as pg_sql
                worker.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
                worker.execute(pg_sql.SQL("SET TRANSACTION SNAPSHOT {}").format(
                    pg_sql.Literal(snapshot.snapshot_id)
                ))
                with adapter.connect() as writer:
                    writer.execute(
                        sql.SQL("INSERT INTO {}.source_rows VALUES (3, 'three')").format(
                            sql.Identifier(self.schema)
                        )
                    )
                count = worker.execute(
                    sql.SQL("SELECT count(*) FROM {}.source_rows").format(
                        sql.Identifier(self.schema)
                    )
                ).fetchone()[0]
                self.assertEqual(count, 2)

    def test_integer_key_bounds_are_read_from_snapshot_connection(self):
        adapter = PostgresAdapter(PostgresEndpoint(DSN))
        with adapter.connect() as conn:
            bounds = integer_key_bounds(conn, self.schema, "source_rows", "id")
        self.assertEqual(bounds, (1, 2))

    def test_integer_key_chunk_reader_uses_non_overlapping_ranges(self):
        adapter = PostgresAdapter(PostgresEndpoint(DSN))
        with adapter.connect() as conn:
            first = list(iter_integer_key_chunk_rows(
                conn, self.schema, "source_rows", "id", 1, 2,
                upper_inclusive=False, page_size=1,
            ))
            second = list(iter_integer_key_chunk_rows(
                conn, self.schema, "source_rows", "id", 2, 2,
                upper_inclusive=True, page_size=1,
            ))
        self.assertEqual([row[0] for row in first], [1])
        self.assertEqual([row[0] for row in second], [2])

    def test_empty_integer_key_returns_no_bounds(self):
        adapter = PostgresAdapter(PostgresEndpoint(DSN))
        with adapter.connect() as conn:
            conn.execute(sql.SQL(
                "CREATE TABLE {}.empty_rows (id bigint PRIMARY KEY)"
            ).format(sql.Identifier(self.schema)))
            bounds = integer_key_bounds(conn, self.schema, "empty_rows", "id")
        self.assertIsNone(bounds)

    def test_binary_copy_transfers_in_fixed_size_blocks(self):
        adapter = PostgresAdapter(PostgresEndpoint(DSN))
        with adapter.connect() as target:
            target.execute(sql.SQL(
                "CREATE TABLE {}.binary_target (id bigint PRIMARY KEY, value text)"
            ).format(sql.Identifier(self.schema)))
            with adapter.connect() as source:
                result = copy_binary_integer_range(
                    source,
                    target,
                    source_schema=self.schema,
                    source_table="source_rows",
                    target_schema=self.schema,
                    target_table="binary_target",
                    columns=("id", "value"),
                    key_column="id",
                    lower_bound=1,
                    upper_bound=2,
                    upper_inclusive=True,
                    block_bytes=8,
                )
            rows = target.execute(sql.SQL(
                "SELECT id, value FROM {}.binary_target ORDER BY id"
            ).format(sql.Identifier(self.schema))).fetchall()
            self.assertEqual(result.rows, 2)
            self.assertGreater(result.bytes_transferred, 0)
            self.assertEqual(rows, [(1, "one"), (2, "two")])

    def test_copy_from_stdin_streams_rows(self):
        adapter = PostgresAdapter(PostgresEndpoint(DSN))
        with adapter.connect() as conn:
            conn.execute(sql.SQL(
                "CREATE TABLE {}.target_rows (id bigint, value text)"
            ).format(sql.Identifier(self.schema)))
            count = copy_rows(
                conn, self.schema, "target_rows", ("id", "value"),
                iter(((1, "one"), (2, "two"), (3, "three"))),
            )
            self.assertEqual(count, 3)
            self.assertEqual(conn.execute(sql.SQL(
                "SELECT count(*) FROM {}.target_rows"
            ).format(sql.Identifier(self.schema))).fetchone()[0], 3)
            conn.commit()


if __name__ == "__main__":
    unittest.main()
