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

**Not complete:** the standalone parallel chunk scheduler is not wired into the demo API; strict LOB-aware per-chunk budgets, durable cross-process orchestration and production crash-recovery tests remain. A table-at-a-time binary COPY demo path is now available, but it is not a production migration service.

## Milestone 1B — PostgreSQL → PostgreSQL snapshot execution (prototype path available; exit gate open)

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
- [x] PostgreSQL binary COPY pipeline transfers chunk data directly between database connections
- [x] COPY data is relayed as binary blocks with a configurable libpq flush threshold (bounded writer backpressure)
- [x] End-to-end integration test covers shared snapshot → parallel integer chunks → target binary COPY

Additional implementation delivered:
- [x] Adaptive integer-key range subdivision driven by exact COUNT(*) and SUM(pg_column_size(row)) measurements inside the imported MVCC snapshot.
- [x] Recursive integer interval splitting with explicit depth guard and no OFFSET pagination.
- [x] Single-key payloads that cannot be subdivided produce an actionable oversized-row / LOB-strategy error.
- [x] PostgreSQL catalog discovery now captures default expressions, generated-column markers and identity-column modes.
- [x] Conservative PostgreSQL target DDL planner for allowlisted built-in types, schemas, tables, nullability, identity columns and primary/unique constraints.
- [x] Generated columns, partitioned tables and unsupported/custom types fail explicitly; unsafe default expressions are reported for review rather than executed.
- [x] Unit tests cover adaptive range coverage, budget subdivision, oversized rows, DDL generation and unsupported-schema diagnostics.

Remaining work:
1. Wire the existing integer/composite keyset and adaptive chunk planners into the API worker pipeline; current demo API uses table-level binary COPY.
2. Add LOB-aware row policy for indivisible oversized records and end-to-end tests proving block-bounded transfer for very large values.
3. Add foreign-key dependency ordering, FK DDL, indexes, check constraints, collations, extensions and generated-column expression translation.
4. Add serial/identity sequence synchronization and target schema-parity validation; CREATE TABLE IF NOT EXISTS alone does not prove an existing target is compatible.
5. Replace demo in-memory job tracking with durable run/task records and wire the target commit protocol to metadata checkpoints.
6. Persist chunk state and checkpoints only after confirmed target commit in the API worker lifecycle.
7. Connect the run orchestrator to the durable task queue and recover expired leases.
8. Add live integration tests with worker termination and commit/checkpoint fault injection.
9. Add deterministic row/bucket reconciliation.


2. Implement explicit source/target transaction ownership, cancellation and graceful worker shutdown.
3. Implement target staging/commit protocol and target-side durable idempotency records.
4. Persist chunk state and checkpoints only after confirmed target commit.
5. Connect the run orchestrator to the durable task queue and recover expired leases.
6. Enforce adaptive per-chunk row/byte budgets and LOB streaming; current binary COPY bounds transfer buffering but does not yet implement LOB-aware splitting.
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

## Phase 2 delivery update — target commit recovery foundation

Implemented in the current iteration:
- Target-local `snowbridge_internal.chunk_commits` ledger written in the same target transaction as each chunk's data.
- Stable chunk identity + immutable plan digest guard; replay with matching identity returns the original commit receipt and does not reapply data.
- Conflicting reuse of a chunk identity with a different digest is rejected.
- Metadata checkpoint writer persists target commit token, row count and byte count after target commit confirmation.
- Ordered chunk execution helper enforces target commit → metadata checkpoint → fenced task acknowledgement.
- Keyless-table fallback creates one deterministic whole-table chunk; binary COPY streams fixed-size blocks, so memory remains bounded. Restart granularity is the whole table, not an individual row range.

Still required before Phase 2 can be declared complete:
- Wire the new chunk execution protocol into a complete run service and worker lifecycle.
- Add deterministic composite-key chunking and resumable chunking for tables without a suitable integer key; the whole-table fallback restarts a failed table from its beginning.
- Add a real LOB policy and end-to-end tests with multi-GB values; current COPY block streaming bounds relay buffers but does not make a single oversized logical row independently restartable.
- Complete DDL dependency discovery/creation (foreign keys, indexes, checks, collations, extensions), generated-column policy, identity/sequence synchronization, and existing-target schema parity validation.
- Add live PostgreSQL fault-injection tests for crash after target commit/before metadata checkpoint, worker lease expiry during load, cancellation and shutdown.
- Add deterministic bucket checksums and deep PK reconciliation with mismatch diagnostics.

The target ledger closes the target-commit/metadata-checkpoint replay gap when callers use the new execution helper. It does not make the two databases one distributed transaction and does not prove content equivalence. Phase 2 remains in progress until the remaining exit gates above pass.


## Phase 2 — Discovery and planning (implementation delivered; live qualification pending)

Implemented on `v2/rebuild`:
- [x] Secret-reference based connection specification and adapter construction for PostgreSQL, MySQL and Oracle; passwords are resolved only at runtime.
- [x] Optional MySQL Connector/Python and python-oracledb dependencies; PostgreSQL remains the default dependency.
- [x] PostgreSQL catalog inventory for tables, ordered columns, defaults, generated/identity markers, primary/usable unique keys, partition flags, row estimates and relation bytes.
- [x] MySQL information_schema inventory for base tables, ordered columns, native type modifiers, nullability, defaults, generated/auto-increment markers, collations, unique indexes/keys, engine, comments and catalog row/byte estimates.
- [x] Oracle ALL_TABLES/ALL_TAB_COLS/ALL_CONSTRAINTS inventory for accessible owners, ordered visible columns, precision/scale/length, defaults, virtual/identity markers, enabled primary/unique constraints, partition flags, comments and statistics-based estimates.
- [x] Shared schema IR extended with catalog byte estimates, storage-engine metadata, comments, indexes, foreign-key and check-constraint extension points.
- [x] Unified capability preflight surfaces configuration and privilege requirements separately from availability.
- [x] Conservative cross-engine type mapping with explicit warning, transform-required and unsupported outcomes; includes Oracle DATE/NUMBER, MySQL unsigned integers, enum/set, LOB and spatial cases.
- [x] Unified discovery report with source inventory, target type mappings, unsupported mapping list, warnings, estimate confidence and explicit estimate assumptions.
- [x] Inventory structural validation rejects empty column sets, invalid ordinals and keys referencing missing columns.
- [x] Optional cross-engine dependency installation documented.

Live qualification still required before calling the exit criterion production-verified:
- Run the optional integration suite against PostgreSQL 16+, MySQL 8.0/8.4 and Oracle 19c/21c/23ai using least-privilege discovery accounts.
- Verify visibility across multiple schemas/owners, restricted catalog grants, quoted identifiers, invisible/hidden columns, partitioned tables, generated columns, composite keys and vendor-specific collations.
- Add catalog queries for foreign-key relationships, check constraints, views/materialized views, triggers, sequences, synonyms, routines, grants and vendor-specific objects before those object classes are included in migration plans.
- Add per-version compatibility coverage and compare catalog estimates against actual row/byte measurements on representative schemas.

Important boundary: Phase 2 inventory supports table/column/key planning; object classes not explicitly discovered must be reported as out of scope rather than assumed migrated. MySQL and Oracle CDC/data-plane execution are not implemented by this milestone.


## Submission iteration — API, UI and executable snapshot demo (delivered on v2/rebuild)

- [x] FastAPI application entry point, health route and interactive OpenAPI documentation.
- [x] Connection-test and schema-discovery HTTP endpoints wired to PostgreSQL, MySQL and Oracle adapters; request credentials are resolved ephemerally and are not persisted.
- [x] Next.js control-plane UI with source/target forms, engine selection, connection test, schema explorer, capability report, catalog estimates and migration progress.
- [x] PostgreSQL-to-PostgreSQL snapshot-only demo endpoint using a consistent exported MVCC snapshot, conservative target DDL, bounded binary COPY blocks and target-local replay ledger.
- [x] Demo migration refuses non-empty target tables and mismatched PostgreSQL major versions; it does not truncate target data.
- [x] Backend API smoke tests and frontend production build in GitHub Actions.
- [x] Latest verified CI run: 59 Python tests passed, 3 optional live vendor tests skipped; metadata migrations applied twice; Next.js production build passed.

**Hard limits of this submission build:**
- The executable migration pipeline is PostgreSQL-to-PostgreSQL only. MySQL and Oracle are available for connection testing and discovery, not data-plane migration.
- The demo migration transfers tables sequentially using a table-level restart unit. It does not yet resume a partially completed multi-table run after process restart.
- Demo job state is process-local memory, not durable. The existing PostgreSQL task lease and checkpoint primitives are not wired into this API.
- CDC, transaction-log capture, deep reconciliation, discrepancy repair/DLQ workflow and enterprise cutover are not implemented.
- The demo copies basic tables/columns and currently omits foreign keys, secondary indexes, views, triggers, routines, grants and sequence synchronization. Unsupported schema constructs may fail explicitly.
- The API has no authentication/RBAC and is intended only for localhost demonstration. Do not expose it to untrusted networks or use it for production/customer data.
- Binary COPY is restricted to matching PostgreSQL major versions and compatible native column types. The target tables must be empty.

### Phase status after this iteration

| Phase | Status |
|---|---|
| 1 — Architecture foundation | Core contracts, metadata schema and credential abstraction implemented; domain boundary tests pass |
| 2 — Discovery and planning | Three adapter discovery paths implemented; live MySQL/Oracle qualification and broader object inventory remain |
| 3 — Snapshot engine | Runnable PostgreSQL-to-PostgreSQL sequential snapshot prototype; parallel chunk orchestration and durable whole-run recovery remain |
| 4 — CDC engine | Not implemented |
| 5 — Reconciliation | Metadata/contracts only; execution and repair not implemented |
| 6 — Orchestration and recovery | Lease/checkpoint primitives exist; not connected to demo API lifecycle |
| 7 — Enterprise cutover | Not implemented |
| 8 — Frontend | Local console for connection testing, discovery and snapshot demo progress implemented; full lifecycle UI remains |
| 9 — Production hardening | CI/build checks exist; authentication, isolation, security review, failure injection and scale qualification remain |
