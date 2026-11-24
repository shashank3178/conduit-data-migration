# Snowbridge V2 — Architecture and delivery status

## Product and branch boundary

Snowbridge is the V2 product identity. It is developed on `v2/rebuild`; `main` remains V1. This branch must not be merged into `main`. The GitHub repository slug remains `conduit-data-migration` for continuity.

## Objective

Build a production-oriented, database-agnostic migration platform with bounded streaming, consistent snapshots, optional CDC, native target bulk loading, durable recovery and verifiable reconciliation. This is a clean rebuild, not a refactor of V1.

## Accepted architecture decisions

- [ADR 0001 — Product and branch boundary](docs/adr/0001-product-and-branch-boundary.md)
- [ADR 0002 — Source/target adapter and capability model](docs/adr/0002-adapter-and-capability-model.md)
- [ADR 0003 — Checkpoint and delivery semantics](docs/adr/0003-checkpoint-and-delivery-semantics.md)
- [ADR 0004 — Snapshot streaming and backpressure](docs/adr/0004-snapshot-streaming-and-backpressure.md)

## Design principles

1. No V1 imports, runtime dependencies or deployment artifacts.
2. Management plane is separate from the database data plane.
3. Vendor-specific behavior stays behind source/target adapter contracts.
4. Capability preflight includes engine version, configuration and permissions.
5. Snapshot readers share one consistent logical snapshot.
6. Data extraction and loading are streaming and bounded by bytes and rows.
7. Checkpoints advance only after confirmed target commit; retries are replay-safe.
8. Reconciliation compares the same logical watermark and explains mismatches.
9. Secrets are references to external secret providers, never plaintext metadata.
10. Resource pressure triggers bounded backpressure rather than unbounded queues.

## Implemented foundation

- Architecture and accepted ADRs: `docs/architecture`, `docs/adr`
- Canonical schema, adapter and event contracts: `backend/src/snowbridge/contracts.py`
- Initial metadata schema and additive durable-lease migration: `backend/sql/0001_metadata_schema.sql`, `backend/sql/0002_durable_task_leases.sql`
- PostgreSQL connectivity, capability preflight, catalog discovery, exported-snapshot helper, integer key-bound discovery, range chunk reader and COPY primitive: `backend/src/snowbridge/adapters/postgresql.py`, `backend/src/snowbridge/snapshot.py`
- Deterministic integer-key partition planning and typed chunk range metadata: `backend/src/snowbridge/partitioning.py`, `backend/src/snowbridge/contracts.py`
- Snapshot-aware range planning and bounded parallel workers: `backend/src/snowbridge/postgresql_snapshot.py`, `backend/src/snowbridge/snapshot_workers.py`
- Byte-block PostgreSQL binary COPY transfer with configurable target libpq flush threshold: `backend/src/snowbridge/bulk_copy.py`
- Bounded parallel workers importing one shared MVCC snapshot, plus snapshot-aware range planning: `backend/src/snowbridge/snapshot_workers.py`, `backend/src/snowbridge/postgresql_snapshot.py`
- Versioned, advisory-locked, checksum-verified metadata migration runner
- PostgreSQL task queue with SKIP LOCKED claiming, lease fencing, heartbeats, bounded retries and terminal failure
- Unit and PostgreSQL integration tests for contracts, configuration, task lease recovery and stale-worker rejection
- Native PostgreSQL local-development instructions: `docs/LOCAL_DEVELOPMENT.md`
- Delivery and exit gates: `docs/IMPLEMENTATION_ROADMAP.md`

The task queue is a metadata-plane primitive, not a complete worker runtime. A task must not be acknowledged until target data is committed using a target-side idempotency protocol.

## Explicitly not production-ready yet

- End-to-end PostgreSQL-to-PostgreSQL run service and management API
- Graceful worker cancellation/shutdown and adaptive row/byte-bounded chunk subdivision
- Adaptive per-chunk row/byte limits and LOB-aware streaming (binary COPY currently streams bounded libpq blocks)
- Target-side idempotency ledger and atomic/replay-safe target commit protocol
- Durable chunk/checkpoint integration with the worker queue
- Schema DDL generation and canonical type conversion
- Deterministic chunk checksums and deep reconciliation/repair
- PostgreSQL CDC slot lifecycle, LSN capture/apply and retention backpressure
- MySQL and Oracle adapters
- UI, authentication/RBAC, external secret-provider implementations, telemetry and cutover
- Production load, chaos, security and 100-GB/1-TB benchmark qualification

Do not treat the PostgreSQL adapter primitives or task queue as a finished migration pipeline. The system must not report migration success until data commit, reconciliation and required cutover gates are implemented and tested.

## Next implementation sequence

1. Complete the PostgreSQL-to-PostgreSQL vertical slice: bounded key-range partitioning, snapshot worker pool, target DDL and COPY, target-side idempotency, durable chunk checkpoints and orchestration.
2. Add deterministic count/checksum/deep-diff reconciliation and failure injection.
3. Add PostgreSQL CDC only after snapshot correctness gates pass.
4. Add the management API and UI against stable migration/run/task contracts.
5. Add MySQL and Oracle adapters based on the same source/target contracts.
6. Complete security, observability, cutover/rollback and scale qualification.

See [implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md) for exit criteria.

## Phase 2 recovery protocol update

The current implementation includes a target-local chunk commit ledger
(`snowbridge_internal.chunk_commits`), a metadata checkpoint writer, an ordered
chunk execution helper, and a streaming whole-table fallback for keyless tables.
These are primitives, not a complete worker runtime. The required order is
target data + ledger commit, metadata checkpoint, then fenced task completion.
A replay with the same stable chunk identity and plan digest returns the
original target commit receipt.

Phase 2 remains in progress: the full run service, composite-key chunking,
resumable keyless-table strategy, complete DDL dependency/sequence support,
target schema parity, fault-injection recovery tests and deterministic
reconciliation are still outstanding. Do not report a migration as successful
until the reconciliation and cutover gates are implemented.


## Phase 2 — Discovery and planning implementation

The branch now includes PostgreSQL, MySQL and Oracle connection adapters and catalog introspection, a shared schema IR with table/column/key metadata and size estimates, capability reports, conservative cross-engine type mapping, and a unified discovery report with unsupported-type diagnostics and estimate confidence. Optional driver installation is documented in README. These are discovery/planning components only; they do not imply CDC or migration execution support for MySQL/Oracle. Live validation against supported server versions and privilege profiles remains a release gate.


## Runnable submission build status

The repository now includes a FastAPI local API and Next.js console. The current executable data path is PostgreSQL-to-PostgreSQL snapshot-only: source MVCC snapshot, conservative target DDL, fixed-block binary COPY and target-side per-table commit ledger. MySQL and Oracle are wired to connection testing and discovery only. API job state remains in memory; CDC, automated reconciliation, durable worker orchestration, cutover and production authentication are not delivered. See `docs/IMPLEMENTATION_ROADMAP.md` and the root README for run instructions and limitations.
