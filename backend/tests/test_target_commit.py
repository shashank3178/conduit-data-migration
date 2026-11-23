import unittest
from uuid import uuid4

from snowbridge.target_commit import ChunkIdentityConflict, commit_chunk


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.in_transaction = True

    def __exit__(self, exc_type, exc, tb):
        self.conn.in_transaction = False
        return False


class FakeConnection:
    def __init__(self):
        self.in_transaction = False
        self.ledger = {}

    def transaction(self):
        return FakeTransaction(self)

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("INSERT INTO snowbridge_internal.chunk_commits"):
            chunk_id, digest = params
            if chunk_id in self.ledger:
                return FakeCursor(None)
            token = uuid4()
            self.ledger[chunk_id] = [digest, token, 0, 0]
            return FakeCursor((token,))
        if normalized.startswith("SELECT payload_digest"):
            digest, token, rows, size = self.ledger[params[0]]
            return FakeCursor((digest, token, rows, size))
        if normalized.startswith("UPDATE snowbridge_internal.chunk_commits"):
            rows, size, chunk_id, token = params
            self.ledger[chunk_id][2:] = [rows, size]
            return FakeCursor(None)
        return FakeCursor(None)


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class ApplyResult:
    rows = 12
    bytes_transferred = 4096


class TargetCommitTests(unittest.TestCase):
    def test_first_attempt_applies_and_records_atomic_receipt(self):
        conn = FakeConnection()
        calls = []
        receipt = commit_chunk(
            conn, chunk_id="table:chunk-1", payload_digest="digest-a",
            apply=lambda active: calls.append(active.in_transaction) or ApplyResult(),
        )
        self.assertEqual(calls, [True])
        self.assertFalse(receipt.already_committed)
        self.assertEqual((receipt.committed_rows, receipt.committed_bytes), (12, 4096))

    def test_replay_skips_data_apply(self):
        conn = FakeConnection()
        first = commit_chunk(
            conn, chunk_id="table:chunk-1", payload_digest="digest-a",
            apply=lambda _: ApplyResult(),
        )
        second = commit_chunk(
            conn, chunk_id="table:chunk-1", payload_digest="digest-a",
            apply=lambda _: self.fail("replay must not apply data twice"),
        )
        self.assertTrue(second.already_committed)
        self.assertEqual(first.commit_token, second.commit_token)
        self.assertEqual(first.committed_rows, second.committed_rows)

    def test_reusing_chunk_identity_with_different_digest_fails(self):
        conn = FakeConnection()
        commit_chunk(
            conn, chunk_id="table:chunk-1", payload_digest="digest-a",
            apply=lambda _: ApplyResult(),
        )
        with self.assertRaises(ChunkIdentityConflict):
            commit_chunk(
                conn, chunk_id="table:chunk-1", payload_digest="digest-b",
                apply=lambda _: ApplyResult(),
            )


if __name__ == "__main__":
    unittest.main()
