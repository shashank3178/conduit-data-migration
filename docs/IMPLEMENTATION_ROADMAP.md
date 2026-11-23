# Snowbridge implementation roadmap

## Milestone 0 — Architecture and domain foundation (completed)

- [x] Product identity and V2 branch boundary
- [x] Architecture decision records
- [x] Canonical domain and adapter contracts
- [x] Initial metadata schema
- [x] Lifecycle/checkpoint contract tests
- [x] CI for Python contracts

## Milestone 1A — PostgreSQL adapter and metadata bootstrap (implemented primitives)

- [x] Psycopg 3 dependency and Snowbridge runtime settings
- [x] PostgreSQL connectivity adapter
- [x] Capability preflight for MVCC snapshots, exported snapshots, logical decoding configuration and COPY
- [x] Catalog discovery for tables, columns, primary and unique keys
- [x] Exported MVCC snapshot keeper and worker import primitive
- [x] Composite-key keyset page reader
- [x] Streaming COPY FROM STDIN writer primitive
- [x] Versioned SQL migration runner with advisory lock and checksum drift detection
- [x] Native local PostgreSQL metadata service (no Docker dependency for local development)
- [x] CI applies metadata schema twice to check idempotent startup
- [x] Durable task lease metadata: fencing token, heartbeat, expiry, attempt limit and retry scheduling
- [x] PostgreSQL task claim/heartbeat/complete/fail operations using SKIP LOCKED and lease fencing
- [x] Metadata migration CLI resolves its DSN from process environment or backend/.env

**Not complete:** a coordinated parallel chunk scheduler, strict per-chunk byte budget/LOB streaming, target-side idempotency ledger, atomic target-commit/checkpoint protocol, end-to-end source-to-target run service, schema DDL translator, API/UI integration, and production-grade crash-recovery tests. The adapter and task-queue primitives must not be treated as a finished migration pipeline.

## Milestone 1B — PostgreSQL → PostgreSQL snapshot execution (in progress)

Implemented in this iteration:
- [x] Deterministic integer-key range planner with non-overlapping half-open ranges and an inclusive final range
- [x] Stable chunk specifications with bound values and safely quoted key identifiers
- [x] PostgreSQL integer MIN/MAX discovery intended to run inside the imported snapshot transaction
- [x] Unit coverage for negative, sparse-width, single-value and invalid range inputs
- [x] PostgreSQL integration coverage for populated and empty integer-key tables
- [x] Bounded parallel snapshot worker pool with a bounded in-flight future window
- [x] Snapshot-aware chunk factory: reads integer MIN/MAX bounds after importing the exported snapshot
- [x] Typed integer range metadata in ChunkSpec; readers compose SQL identifiers and bind range values
- [x] Integration tests verify concurrent source writes remain invisible to all workers sharing the exported snapshot
- [x] Integration tests exercise planning and reading multiple integer-key chunks

Remaining work:
1. Add adaptive chunk subdivision so skewed/sparse key ranges obey actual per-chunk row limits.
2. Implement explicit source/target transaction ownership, cancellation and graceful worker shutdown.
3. Implement target staging/commit protocol and target-side durable idempotency records.
4. Persist chunk state and checkpoints only after confirmed target commit.
5. Connect the run orchestrator to the durable task queue and recover expired leases.
6. Enforce byte budgets and LOB streaming, not only row limits.
7. Add live integration tests with worker termination and commit/checkpoint fault injection.
8. Add deterministic row/bucket reconciliation.

**Exit gates:** no fractured snapshot, no whole-table buffering, bounded bytes and connections, replay-safe target commit/checkpoint gap, no missing/extra/mutated rows, and restart without full-run restart.

## Milestone 2 — PostgreSQL CDC

Logical decoding capability preflight, publication/slot lifecycle, LSN checkpointing, transaction ordering, retention pressure controls, replay-safe target apply and DDL drift policy.

## Milestone 3 — MySQL adapters

InnoDB consistent snapshot coordinated with GTID/binlog boundary, indexed key ranges, row-based binlog capture, LOAD DATA/staging and type-semantic handling.

## Milestone 4 — Oracle adapters

SCN-consistent reads, approved LogMiner/XStream capture strategy, ROWID/key chunking, array binds/direct-path load, LOB streaming and NUMBER/DATE/empty-string semantics. Licensing and permissions are preflight gates.

## Milestone 5 — Reconciliation, cutover and production hardening

Deep PK diff/repair, durable DLQ, cutover gate, rollback strategy, multi-tenant RBAC, audit, secret rotation, telemetry, chaos/recovery and scale benchmarks.

## Pairing sequence

PostgreSQL→PostgreSQL; MySQL→PostgreSQL; PostgreSQL→MySQL; MySQL→MySQL; Oracle→PostgreSQL; PostgreSQL→Oracle; then additional pairs based on customer demand. Implement adapters and capabilities, not a separate engine per pair.
