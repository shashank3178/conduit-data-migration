"""PostgreSQL integration tests for durable task lease fencing and retries."""
from __future__ import annotations

import os
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql

from snowbridge.metadata.task_queue import (
    LeaseLostError,
    claim_task,
    complete_task,
    fail_task,
)


DSN = os.getenv("SNOWBRIDGE_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "SNOWBRIDGE_TEST_DATABASE_URL is not configured")
class DurableTaskQueueIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "sb_queue_" + uuid4().hex[:12]
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
            conn.execute("""
                CREATE TABLE migration_tasks (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    run_id uuid NOT NULL,
                    task_type text NOT NULL,
                    object_schema text,
                    object_name text,
                    state text NOT NULL DEFAULT 'pending',
                    priority integer NOT NULL DEFAULT 100,
                    attempt integer NOT NULL DEFAULT 0,
                    max_attempts integer NOT NULL DEFAULT 5,
                    lease_owner text,
                    lease_token uuid,
                    lease_expires_at timestamptz,
                    leased_at timestamptz,
                    heartbeat_at timestamptz,
                    available_at timestamptz NOT NULL DEFAULT now(),
                    completed_at timestamptz,
                    last_error_category text,
                    last_error_detail text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            self.run_id = uuid4()
            self.task_id = conn.execute(
                """
                INSERT INTO migration_tasks(run_id, task_type, object_schema, object_name)
                VALUES (%s, 'snapshot_chunk', 'public', 'orders')
                RETURNING id
                """,
                (self.run_id,),
            ).fetchone()[0]

    def tearDown(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(self.schema)
            ))

    def connect(self):
        conn = psycopg.connect(DSN)
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        return conn

    def test_expired_lease_is_reclaimed_and_stale_worker_is_fenced(self):
        with self.connect() as conn:
            first = claim_task(conn, "worker-a", lease_seconds=60)
            self.assertIsNotNone(first)
            conn.execute(
                "UPDATE migration_tasks SET lease_expires_at = now() - interval '1 second' WHERE id = %s",
                (self.task_id,),
            )
            second = claim_task(conn, "worker-b", lease_seconds=60)
            self.assertIsNotNone(second)
            self.assertNotEqual(first.lease_token, second.lease_token)
            with self.assertRaises(LeaseLostError):
                complete_task(conn, first.task_id, first.owner, first.lease_token)
            complete_task(conn, second.task_id, second.owner, second.lease_token)
            state = conn.execute(
                "SELECT state FROM migration_tasks WHERE id = %s", (self.task_id,)
            ).fetchone()[0]
            self.assertEqual(state, "succeeded")

    def test_retry_is_bounded_by_max_attempts(self):
        with self.connect() as conn:
            conn.execute(
                "UPDATE migration_tasks SET max_attempts = 2 WHERE id = %s",
                (self.task_id,),
            )
            first = claim_task(conn, "worker-a")
            self.assertEqual(
                fail_task(conn, first.task_id, first.owner, first.lease_token,
                          "transient", "connection interrupted", retry_delay_seconds=0),
                "retry",
            )
            second = claim_task(conn, "worker-b")
            self.assertEqual(second.attempt, 2)
            self.assertEqual(
                fail_task(conn, second.task_id, second.owner, second.lease_token,
                          "permanent", "conversion failed", retry_delay_seconds=0),
                "failed",
            )
            self.assertIsNone(claim_task(conn, "worker-c"))


if __name__ == "__main__":
    unittest.main()
