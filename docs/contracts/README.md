# Domain and adapter contracts

The executable reference contracts are under `backend/src/snowbridge/contracts.py`. They intentionally use Python standard-library types so the domain boundary is testable without vendor drivers.

## Canonical schema IR

Represent catalog facts independently of SQL dialect: schemas, tables, columns, keys, indexes, constraints, generated/identity semantics, comments and source-native type details. A type mapping is classified as `automatic`, `warning`, `requires_transform` or `unsupported`. Preserve source type metadata; never silently truncate precision, timezone or character data.

## Source adapter

- `inspect_capabilities()`
- `discover_schema()`
- `begin_consistent_snapshot()`
- `read_snapshot_chunk()`
- optional `start_cdc()` and `read_cdc()`

The snapshot handle owns the database-specific consistency token and lifecycle. Parallel workers must import/use the same token where the engine supports exported snapshots. The adapter documents whether its handle pins a transaction, SCN or log retention.

## Target adapter

- `inspect_capabilities()`
- `apply_schema()`
- `bulk_load()`
- `apply_changes()`
- `synchronize_sequences()`
- optional `reconcile_bucket()`

A bulk-load result includes committed row/byte counts and a stable target commit token when available. The target adapter documents atomicity and replay semantics.

## Capability record

Every capability includes status, reason, requirements, permission checks and optional version constraints. Preflight aggregates missing capabilities and blocks unsafe plans.

## Chunk and checkpoint

A chunk has stable ID, table identity, range predicate/bounds, snapshot ID, row/byte limits and attempt metadata. A checkpoint refers to a completed chunk and source boundary. It may be advanced only after target commit.

## CDC event

Canonical events preserve operation, PK (including composite keys), before/after images where available, source log position, transaction ID, transaction sequence and transaction-end marker. Capture timestamp is observability metadata, not an ordering key.

## Compatibility policy

Contracts are versioned. Adapter changes must pass a shared contract suite for snapshot consistency, bounded memory, error classification, cancellation, idempotency and replay.
