import unittest
from uuid import uuid4

from snowbridge.metadata.checkpoints import CheckpointConflict
from snowbridge.target_commit import TargetCommitReceipt


class CheckpointContractTests(unittest.TestCase):
    def test_conflicting_checkpoint_evidence_has_explicit_error_type(self):
        self.assertTrue(issubclass(CheckpointConflict, RuntimeError))

    def test_receipt_is_stable_commit_evidence(self):
        token = uuid4()
        receipt = TargetCommitReceipt(
            "orders:chunk-1", "plan-digest", token, 10, 2048, False
        )
        self.assertEqual(receipt.commit_token, token)
        self.assertEqual(receipt.committed_rows, 10)
        self.assertEqual(receipt.committed_bytes, 2048)


if __name__ == "__main__":
    unittest.main()
