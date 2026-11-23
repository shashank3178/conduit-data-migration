"""Integration coverage for parallel readers sharing one MVCC snapshot."""
from __future__ import annotations

import os
import threading
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql

from snowbridge.adapters.postgresql import PostgresAdapter, PostgresEndpoint
from snowbridge.contracts import ChunkSpec
from snowbridge.snapshot_workers import iter_snapshot_chunks


DSN = os.getenv("SNOWBRIDGE_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "SNOWBRIDGE_TEST_DATABASE_URL is not configured")
class SnapshotWorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "sb_workers_" + uuid4().hex[:12]
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL(
                "CREATE TABLE {}.source_rows (id bigint PRIMARY KEY, value text)"
            ).format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL(
                "INSERT INTO {}.source_rows VALUES (1, 'one'), (2, 'two')"
            ).format(sql.Identifier(self.schema)))
        self.adapter = PostgresAdapter(PostgresEndpoint(DSN))

    def tearDown(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(self.schema)
            ))

    def test_workers_observe_same_exported_snapshot_after_concurrent_write(self):
        writer_can_start = threading.Event()
        writer_committed = threading.Event()
        writer_errors = []

        def writer():
            if not writer_can_start.wait(timeout=10):
                writer_errors.append(TimeoutError("snapshot workers did not start"))
                return
            try:
                with self.adapter.connect() as conn:
                    conn.execute(sql.SQL(
                        "INSERT INTO {}.source_rows VALUES (3, 'three')"
                    ).format(sql.Identifier(self.schema)))
            except BaseException as exc:
                writer_errors.append(exc)
            finally:
                writer_committed.set()

        writer_thread = threading.Thread(target=writer, daemon=True)
        writer_thread.start()

        def chunks(snapshot):
            return (
                ChunkSpec(
                    chunk_id=f"snapshot-test-{index}",
                    schema_name=self.schema,
                    table_name="source_rows",
                    snapshot_id=snapshot.snapshot_id,
                    predicate="TRUE",
                )
                for index in range(2)
            )

        def read_count(conn, chunk):
            writer_can_start.set()
            if not writer_committed.wait(timeout=10):
                raise TimeoutError("concurrent writer did not commit")
            return conn.execute(sql.SQL(
                "SELECT count(*) FROM {}.source_rows"
            ).format(sql.Identifier(self.schema))).fetchone()[0]

        results = list(iter_snapshot_chunks(
            self.adapter, chunks, read_count, worker_count=2, max_in_flight=2
        ))
        writer_thread.join(timeout=10)
        self.assertFalse(writer_thread.is_alive())
        self.assertEqual(writer_errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual({value for _, value in results}, {2})

    def test_invalid_worker_window_is_rejected_before_connecting(self):
        with self.assertRaises(ValueError):
            list(iter_snapshot_chunks(
                self.adapter, lambda snapshot: (), lambda conn, chunk: None,
                worker_count=2, max_in_flight=1,
            ))


if __name__ == "__main__":
    unittest.main()
