"""PostgreSQL-backed durable task claiming with lease fencing.

This module owns metadata-plane task state only. A worker must commit target
data first, using a target-side idempotency protocol, before acknowledging the
metadata task. The metadata database cannot make a transaction atomic with an
unrelated target database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


class LeaseLostError(RuntimeError):
    """Raised when a worker attempts to mutate a task using a stale lease."""


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    task_id: UUID
    run_id: UUID
    task_type: str
    object_schema: str | None
    object_name: str | None
    attempt: int
    max_attempts: int
    owner: str
    lease_token: UUID
    lease_expires_at: datetime


def claim_task(conn: Any, worker_id: str, lease_seconds: int = 60) -> ClaimedTask | None:
    """Atomically claim one eligible task; expired leases are recoverable.

    FOR UPDATE SKIP LOCKED allows independent workers to claim concurrently.
    The lease token is a fencing token: a worker whose lease was replaced can
    no longer heartbeat, fail, or complete the task.
    """
    if not worker_id.strip():
        raise ValueError("worker_id is required")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")

    with conn.transaction():
        conn.execute(
            """
            UPDATE migration_tasks
               SET state = 'failed',
                   lease_owner = NULL,
                   lease_token = NULL,
                   lease_expires_at = NULL,
                   updated_at = clock_timestamp()
             WHERE state = 'running'
               AND lease_expires_at <= clock_timestamp()
               AND attempt >= max_attempts
            """
        )
        row = conn.execute(
            """
            WITH candidate AS (
                SELECT id
                  FROM migration_tasks
                 WHERE attempt < max_attempts
                   AND (
                       (state IN ('pending', 'retry')
                        AND available_at <= clock_timestamp())
                       OR
                       (state = 'running'
                        AND lease_expires_at <= clock_timestamp())
                   )
                 ORDER BY priority, available_at, created_at
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1
            )
            UPDATE migration_tasks AS task
               SET state = 'running',
                   attempt = task.attempt + 1,
                   lease_owner = %s,
                   lease_token = gen_random_uuid(),
                   lease_expires_at = clock_timestamp()
                       + make_interval(secs => %s),
                   leased_at = clock_timestamp(),
                   heartbeat_at = clock_timestamp(),
                   updated_at = clock_timestamp()
              FROM candidate
             WHERE task.id = candidate.id
            RETURNING task.id, task.run_id, task.task_type,
                      task.object_schema, task.object_name,
                      task.attempt, task.max_attempts, task.lease_owner,
                      task.lease_token, task.lease_expires_at
            """,
            (worker_id, lease_seconds),
        ).fetchone()

    if row is None:
        return None
    return ClaimedTask(
        task_id=row[0],
        run_id=row[1],
        task_type=row[2],
        object_schema=row[3],
        object_name=row[4],
        attempt=row[5],
        max_attempts=row[6],
        owner=row[7],
        lease_token=row[8],
        lease_expires_at=row[9],
    )


def heartbeat_task(
    conn: Any, task_id: UUID, worker_id: str, lease_token: UUID,
    lease_seconds: int = 60,
) -> datetime:
    """Extend a still-valid lease; stale or expired workers are fenced out."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    with conn.transaction():
        row = conn.execute(
            """
            UPDATE migration_tasks
               SET heartbeat_at = clock_timestamp(),
                   lease_expires_at = clock_timestamp()
                       + make_interval(secs => %s),
                   updated_at = clock_timestamp()
             WHERE id = %s AND state = 'running'
               AND lease_owner = %s AND lease_token = %s
               AND lease_expires_at > clock_timestamp()
            RETURNING lease_expires_at
            """,
            (lease_seconds, task_id, worker_id, lease_token),
        ).fetchone()
    if row is None:
        raise LeaseLostError(f"task {task_id} lease is no longer owned by {worker_id}")
    return row[0]


def complete_task(
    conn: Any, task_id: UUID, worker_id: str, lease_token: UUID,
) -> None:
    """Acknowledge only while the exact, unexpired lease is still owned."""
    with conn.transaction():
        result = conn.execute(
            """
            UPDATE migration_tasks
               SET state = 'succeeded',
                   completed_at = clock_timestamp(),
                   lease_owner = NULL,
                   lease_token = NULL,
                   lease_expires_at = NULL,
                   updated_at = clock_timestamp()
             WHERE id = %s AND state = 'running'
               AND lease_owner = %s AND lease_token = %s
               AND lease_expires_at > clock_timestamp()
            """,
            (task_id, worker_id, lease_token),
        )
    if result.rowcount != 1:
        raise LeaseLostError(f"task {task_id} lease is no longer owned by {worker_id}")


def fail_task(
    conn: Any, task_id: UUID, worker_id: str, lease_token: UUID,
    error_category: str, sanitized_detail: str,
    retry_delay_seconds: int = 5,
) -> str:
    """Schedule a bounded retry or terminally fail after max_attempts."""
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")
    if not error_category.strip():
        raise ValueError("error_category is required")
    with conn.transaction():
        row = conn.execute(
            """
            UPDATE migration_tasks
               SET state = CASE WHEN attempt < max_attempts
                                THEN 'retry' ELSE 'failed' END,
                   available_at = clock_timestamp()
                       + make_interval(secs => %s),
                   last_error_category = %s,
                   last_error_detail = %s,
                   lease_owner = NULL,
                   lease_token = NULL,
                   lease_expires_at = NULL,
                   updated_at = clock_timestamp()
             WHERE id = %s AND state = 'running'
               AND lease_owner = %s AND lease_token = %s
               AND lease_expires_at > clock_timestamp()
            RETURNING state
            """,
            (
                retry_delay_seconds, error_category, sanitized_detail[:2000],
                task_id, worker_id, lease_token,
            ),
        ).fetchone()
    if row is None:
        raise LeaseLostError(f"task {task_id} lease is no longer owned by {worker_id}")
    return row[0]
