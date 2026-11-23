"""Replay-safe target chunk commits.

The ledger is stored in the target database and committed in the same
transaction as the chunk's data. Metadata checkpoints are deliberately written
after this transaction commits; a crash in that gap is recovered by replaying
the same chunk identity and digest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID


class ChunkIdentityConflict(RuntimeError):
    """A stable chunk identity was reused for different planned content."""


@dataclass(frozen=True, slots=True)
class TargetCommitReceipt:
    chunk_id: str
    payload_digest: str
    commit_token: UUID
    committed_rows: int
    committed_bytes: int
    already_committed: bool


def ensure_target_commit_ledger(conn: Any) -> None:
    """Create the target-local ledger. Safe to call before every chunk."""
    conn.execute("CREATE SCHEMA IF NOT EXISTS snowbridge_internal")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snowbridge_internal.chunk_commits (
            chunk_id text PRIMARY KEY,
            payload_digest text NOT NULL,
            commit_token uuid NOT NULL,
            committed_rows bigint NOT NULL CHECK (committed_rows >= 0),
            committed_bytes bigint NOT NULL CHECK (committed_bytes >= 0),
            committed_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
        """
    )


def commit_chunk(
    conn: Any,
    *,
    chunk_id: str,
    payload_digest: str,
    apply: Callable[[Any], Any],
) -> TargetCommitReceipt:
    """Apply data and ledger atomically, or return the previous commit.

    The apply callback runs inside the target transaction and must return an
    object with non-negative rows and bytes_transferred attributes. It must
    not commit or change transaction ownership. The digest identifies the
    immutable source snapshot + table + chunk plan; it is not a substitute
    for content reconciliation.
    """
    if not chunk_id.strip() or not payload_digest.strip():
        raise ValueError("chunk_id and payload_digest are required")

    with conn.transaction():
        ensure_target_commit_ledger(conn)
        inserted = conn.execute(
            """
            INSERT INTO snowbridge_internal.chunk_commits
                (chunk_id, payload_digest, commit_token,
                 committed_rows, committed_bytes)
            VALUES (%s, %s, gen_random_uuid(), 0, 0)
            ON CONFLICT (chunk_id) DO NOTHING
            RETURNING commit_token
            """,
            (chunk_id, payload_digest),
        ).fetchone()

        if inserted is None:
            previous = conn.execute(
                """
                SELECT payload_digest, commit_token, committed_rows, committed_bytes
                  FROM snowbridge_internal.chunk_commits
                 WHERE chunk_id = %s
                 FOR UPDATE
                """,
                (chunk_id,),
            ).fetchone()
            if previous is None:
                raise RuntimeError("target commit ledger row disappeared during replay")
            if previous[0] != payload_digest:
                raise ChunkIdentityConflict(
                    f"chunk {chunk_id!r} already committed with a different payload digest"
                )
            return TargetCommitReceipt(
                chunk_id, payload_digest, previous[1], int(previous[2]),
                int(previous[3]), True,
            )

        result = apply(conn)
        rows = getattr(result, "rows", None)
        byte_count = getattr(result, "bytes_transferred", None)
        if (isinstance(rows, bool) or not isinstance(rows, int) or rows < 0
                or isinstance(byte_count, bool) or not isinstance(byte_count, int)
                or byte_count < 0):
            raise ValueError("chunk apply must return non-negative integer rows and bytes_transferred")

        token = inserted[0]
        conn.execute(
            """
            UPDATE snowbridge_internal.chunk_commits
               SET committed_rows = %s, committed_bytes = %s
             WHERE chunk_id = %s AND commit_token = %s
            """,
            (rows, byte_count, chunk_id, token),
        )
        return TargetCommitReceipt(
            chunk_id, payload_digest, token, rows, byte_count, False
        )
