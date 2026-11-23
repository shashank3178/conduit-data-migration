"""Bounded parallel readers sharing one PostgreSQL MVCC snapshot.

The source snapshot owner remains open until every submitted worker finishes.
Only a bounded number of futures are submitted at once, so planning a large
table inventory does not create an unbounded in-memory work queue.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable, Iterable, Iterator, TypeVar

from snowbridge.adapters.postgresql import PostgresAdapter
from snowbridge.contracts import ChunkSpec
from snowbridge.snapshot import ExportedSnapshot

T = TypeVar("T")


def iter_snapshot_chunks(
    adapter: PostgresAdapter,
    chunks: Iterable[ChunkSpec],
    handler: Callable[[object, ChunkSpec], T],
    *,
    worker_count: int = 4,
    max_in_flight: int | None = None,
) -> Iterator[tuple[ChunkSpec, T]]:
    """Yield completed chunk results while workers share one exported snapshot.

    The handler receives an already-connected worker connection with the
    exported snapshot imported as its first transaction-level operation. It
    must finish source reads before returning; this function commits/closes the
    connection. Target writes and metadata acknowledgements belong to later
    pipeline stages and must not be hidden inside this source helper.
    """
    if worker_count <= 0:
        raise ValueError("worker_count must be positive")
    window = max_in_flight if max_in_flight is not None else worker_count * 2
    if window < worker_count or window <= 0:
        raise ValueError("max_in_flight must be >= worker_count")

    source = iter(chunks)
    exhausted = False
    pending: dict[Future[T], ChunkSpec] = {}

    with ExportedSnapshot(adapter) as snapshot:
        def execute(chunk: ChunkSpec) -> T:
            if chunk.snapshot_id != snapshot.snapshot_id:
                raise ValueError(
                    f"chunk {chunk.chunk_id} references a different snapshot"
                )
            with adapter.connect() as worker_connection:
                # This must be the first transaction operation on this connection.
                ExportedSnapshot(adapter, handle=snapshot).import_into(worker_connection)
                return handler(worker_connection, chunk)

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            try:
                while pending or not exhausted:
                    while not exhausted and len(pending) < window:
                        try:
                            chunk = next(source)
                        except StopIteration:
                            exhausted = True
                            break
                        future = executor.submit(execute, chunk)
                        pending[future] = chunk

                    if not pending:
                        continue

                    completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in completed:
                        chunk = pending.pop(future)
                        yield chunk, future.result()
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
