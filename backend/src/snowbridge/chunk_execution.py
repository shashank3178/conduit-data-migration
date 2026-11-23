"""Ordered chunk execution across target commit and metadata checkpoint.

Target data + target ledger commit first, metadata checkpoint second, task
acknowledgement last. A crash at either boundary is safe to replay.
"""
from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from snowbridge.metadata.checkpoints import record_chunk_checkpoint
from snowbridge.metadata.task_queue import complete_task
from snowbridge.target_commit import TargetCommitReceipt, commit_chunk


def execute_chunk(
    *,
    target_conn: Any,
    metadata_conn: Any,
    chunk_id: str,
    payload_digest: str,
    apply: Callable[[Any], Any],
    run_id: UUID,
    task_id: UUID,
    metadata_chunk_id: UUID,
    snapshot_id: str,
    worker_id: str,
    lease_token: UUID,
    source_position: dict[str, Any] | None = None,
) -> TargetCommitReceipt:
    """Execute the durable protocol in its required order.

    If target commit succeeds but checkpointing fails, the caller must retry
    with the same chunk_id and payload_digest. The target ledger returns the
    prior receipt without applying rows again, then the checkpoint is written.
    The task is acknowledged only after the checkpoint transaction succeeds.
    """
    receipt = commit_chunk(
        target_conn,
        chunk_id=chunk_id,
        payload_digest=payload_digest,
        apply=apply,
    )
    record_chunk_checkpoint(
        metadata_conn,
        run_id=run_id,
        task_id=task_id,
        metadata_chunk_id=metadata_chunk_id,
        snapshot_id=snapshot_id,
        receipt=receipt,
        source_position=source_position,
    )
    complete_task(metadata_conn, task_id, worker_id, lease_token)
    return receipt
