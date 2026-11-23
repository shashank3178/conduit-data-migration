"""Metadata checkpoint persistence after target-side commit confirmation."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from snowbridge.target_commit import TargetCommitReceipt


class CheckpointConflict(RuntimeError):
    """Metadata already contains different commit evidence for a chunk."""


def record_chunk_checkpoint(
    conn: Any,
    *,
    run_id: UUID,
    task_id: UUID,
    metadata_chunk_id: UUID,
    snapshot_id: str,
    receipt: TargetCommitReceipt,
    source_position: dict[str, Any] | None = None,
) -> None:
    """Persist checkpoint evidence only after commit_chunk returned.

    This metadata transaction is intentionally separate from the target
    transaction. Repeating it is safe; conflicting evidence is rejected.
    """
    if not snapshot_id:
        raise ValueError("snapshot_id is required")
    with conn.transaction():
        existing = conn.execute(
            """
            SELECT target_commit_token, committed_rows, committed_bytes
              FROM migration_checkpoints
             WHERE chunk_id = %s
             FOR UPDATE
            """,
            (metadata_chunk_id,),
        ).fetchone()
        expected = (
            str(receipt.commit_token), receipt.committed_rows,
            receipt.committed_bytes,
        )
        if existing is not None:
            actual = (str(existing[0]), int(existing[1]), int(existing[2]))
            if actual != expected:
                raise CheckpointConflict(
                    f"chunk {metadata_chunk_id} already has different commit evidence"
                )
            return

        updated = conn.execute(
            """
            UPDATE migration_chunks
               SET state = 'succeeded',
                   rows_committed = %s,
                   bytes_committed = %s,
                   target_commit_token = %s,
                   completed_at = clock_timestamp()
             WHERE id = %s AND task_id = %s
            """,
            (
                receipt.committed_rows, receipt.committed_bytes,
                str(receipt.commit_token), metadata_chunk_id, task_id,
            ),
        )
        if updated.rowcount != 1:
            raise ValueError("metadata chunk does not belong to the supplied task")

        conn.execute(
            """
            INSERT INTO migration_checkpoints
                (run_id, task_id, chunk_id, source_position,
                 target_commit_token, committed_rows, committed_bytes)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                run_id, task_id, metadata_chunk_id,
                json.dumps(source_position) if source_position is not None else None,
                str(receipt.commit_token), receipt.committed_rows,
                receipt.committed_bytes,
            ),
        )
