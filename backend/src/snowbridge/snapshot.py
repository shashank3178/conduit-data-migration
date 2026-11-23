"""PostgreSQL exported-snapshot lifecycle helpers."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from snowbridge.adapters.postgresql import PostgresAdapter
from snowbridge.contracts import SnapshotHandle


@dataclass
class ExportedSnapshot(AbstractContextManager):
    """Keeps the exporting transaction alive until all workers finish importing."""
    adapter: PostgresAdapter
    connection: Any = None
    handle: SnapshotHandle | None = None

    def __enter__(self) -> SnapshotHandle:
        self.connection = self.adapter.connect()
        self.connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot_id = self.connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
        self.handle = SnapshotHandle(
            snapshot_id=snapshot_id,
            consistency_token=snapshot_id,
            created_at=self.connection.execute("SELECT transaction_timestamp()").fetchone()[0],
        )
        return self.handle

    def import_into(self, worker_connection: Any) -> None:
        """Import before any query in worker transaction; identifier is safely quoted."""
        if self.handle is None:
            raise RuntimeError("snapshot has not been opened")
        from psycopg import sql
        worker_connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        worker_connection.execute(
            sql.SQL("SET TRANSACTION SNAPSHOT {}").format(sql.Literal(self.handle.snapshot_id))
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.connection is not None:
            self.connection.rollback()
            self.connection.close()
        self.connection = None
        self.handle = None
