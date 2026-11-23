from datetime import datetime, timedelta, timezone
import unittest

from snowbridge.contracts import (
    BulkLoadResult,
    Capability,
    CapabilityStatus,
    Checkpoint,
    ChunkSpec,
    RunState,
    SourcePosition,
    assert_checkpoint_after_commit,
    transition_run,
)


class ContractTests(unittest.TestCase):
    def test_happy_path_state_transitions(self):
        state = RunState.DRAFT
        for target in (
            RunState.PREFLIGHT,
            RunState.SNAPSHOT,
            RunState.RECONCILIATION,
            RunState.CUTOVER_READY,
            RunState.CUTOVER,
            RunState.COMPLETED,
        ):
            state = transition_run(state, target)
        self.assertEqual(state, RunState.COMPLETED)

    def test_terminal_state_cannot_restart(self):
        with self.assertRaises(ValueError):
            transition_run(RunState.COMPLETED, RunState.SNAPSHOT)

    def test_invalid_transition_is_rejected(self):
        with self.assertRaises(ValueError):
            transition_run(RunState.DRAFT, RunState.CUTOVER)

    def test_checkpoint_must_match_committed_target_result(self):
        result = BulkLoadResult(10, 2048, "commit-123", "chunk-abc")
        checkpoint = Checkpoint(
            "task-1", "chunk-1", "snapshot-1", "commit-123", 10, 2048,
            SourcePosition("lsn", "0/16B6C50"),
        )
        assert_checkpoint_after_commit(result, checkpoint)

    def test_checkpoint_mismatch_is_rejected(self):
        result = BulkLoadResult(10, 2048, "commit-123", "chunk-abc")
        checkpoint = Checkpoint("task-1", "chunk-1", "snapshot-1", "commit-old", 10, 2048)
        with self.assertRaises(ValueError):
            assert_checkpoint_after_commit(result, checkpoint)

    def test_chunk_requires_positive_limits_and_stable_identity(self):
        with self.assertRaises(ValueError):
            ChunkSpec("c1", "public", "items", "s1", "id > %s", max_bytes=0)

    def test_capability_requires_explanation(self):
        cap = Capability("logical_replication", CapabilityStatus.REQUIRES_PERMISSION,
                         "replication role is missing", permission_checks=("REPLICATION",))
        self.assertFalse(cap.usable)
        self.assertIn("missing", cap.reason)


if __name__ == "__main__":
    unittest.main()
