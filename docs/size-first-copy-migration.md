# Size-first PostgreSQL COPY migration

## Execution contract
- PostgreSQL COPY is the default writer and the only normal engine offered in the migration execution UI.
- Source extraction uses a named/server-side cursor and an 8 MiB serialized-payload target per durable checkpoint. Configure with `CONDUIT_COPY_CHUNK_BYTES`; the worker clamps it between 1 MiB and 64 MiB.
- Primary keys are retained only as deterministic resume positions. They do not size chunks or calculate throughput.
- Destination writes COPY into a transaction-local staging table, then merge atomically. Metadata checkpoints are committed only after the destination transaction succeeds.
- Transfer throughput and progress are expressed in bytes. Row counts remain secondary diagnostics for explaining conflicts and rejected records.

## Discovery and planning
Plan creation refreshes both selected live catalogs. Discovery records `pg_total_relation_size` for regular tables (heap, indexes and TOAST), and the planning UI displays this footprint as its primary table-selection signal. Row estimates are diagnostic only.

## Validation
Validation first streams deterministic PostgreSQL COPY text output, ordered by mapped primary key, into SHA-256 digests. Matching digests validate the mapped data without materializing table contents. When digests differ, validation falls back to exact mapped-column comparison and reports missing destination data, extra destination data, type mismatches, column-value mismatches and bounded key/column samples. Fingerprint failures are retained as explicit diagnostics rather than silently treated as success.

## Production limitations
- 8 MiB is a starting target, not a universal optimum; benchmark against endpoint CPU, network, WAL and storage throughput.
- Serialized logical payload bytes are not wire bytes or physical relation bytes; UI comparisons against physical table footprint are approximate.
- Primary-key checkpoints do not provide a consistent cross-table snapshot while a mutable source is being written. Online enterprise migration requires a coordinated snapshot plus CDC/WAL catch-up.
- Run real PostgreSQL integration tests for TOAST, JSON/JSONB, generated/identity columns, triggers, FK ordering, UPSERT conflicts, cancellation and worker crash/recovery.
