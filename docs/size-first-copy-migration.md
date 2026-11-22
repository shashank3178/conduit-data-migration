# Size-first PostgreSQL COPY migration

## Execution contract

- PostgreSQL COPY is the default data writer; the execution page presents COPY as the primary engine.
- Source extraction uses a named/server-side cursor and an 8 MiB serialized-payload target per durable checkpoint. Configure with `CONDUIT_COPY_CHUNK_BYTES`; the worker clamps it between 1 MiB and 64 MiB.
- Primary keys remain only as deterministic resume positions. They do not size chunks or calculate throughput.
- Destination writes use COPY into a transaction-local staging table followed by a transactional INSERT/UPSERT merge. A metadata checkpoint is committed only after the destination transaction succeeds.
- Transfer throughput and progress are expressed in bytes. Row counts remain secondary diagnostics for write conflicts and rejected records.

## Discovery and planning

Plan creation refreshes both selected live catalogs. Discovery records `pg_total_relation_size` for regular tables (heap, indexes and TOAST), and planning displays this footprint as the primary table-selection signal. Row estimates are retained only as diagnostics.

## Validation

Validation remains an exact primary-key-aligned streaming comparison of mapped values. It uses server-side cursor windows and records logical bytes compared on both sides. Diagnostics distinguish missing destination data, extra destination data, type mismatches, column-value mismatches, and validation execution failures, with bounded key/column samples. Exact comparison is retained instead of replacing correctness with a lossy aggregate checksum.

## Limitations requiring further production work

- 8 MiB is a starting target, not a universal optimum; benchmark against endpoint CPU, network, WAL and storage throughput.
- The chunk size is based on serialized logical payload bytes, not wire bytes or physical relation bytes. Comparing logical bytes to physical table footprint is approximate.
- A primary-key checkpoint does not create a consistent cross-table snapshot while a mutable source is being written. Production online migration needs a coordinated snapshot and CDC/WAL catch-up.
- Run live PostgreSQL integration tests for large TOAST values, JSON/JSONB, generated/identity columns, triggers, FK ordering, UPSERT conflicts, cancellation and worker crash/recovery.
