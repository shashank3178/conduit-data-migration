"""Real PostgreSQL adapter tests; enabled by SNOWBRIDGE_TEST_DATABASE_URL."""
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql

from snowbridge.adapters.postgresql import PostgresAdapter, PostgresEndpoint, copy_rows
from snowbridge.snapshot import ExportedSnapshot


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
