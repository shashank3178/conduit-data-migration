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

## Deliverables in this branch

- Architecture and accepted ADRs: `docs/architecture`, `docs/adr`
- Canonical schema, adapter and event contracts: `backend/src/snowbridge/contracts.py`
- Metadata schema proposal: `backend/sql/0001_metadata_schema.sql`
- Contract tests: `backend/tests/test_contracts.py`
- Operational recovery and security design: `docs/OPERATIONS.md`
- Test/benchmark plan: `docs/TEST_STRATEGY.md`
- Phased implementation roadmap: `docs/IMPLEMENTATION_ROADMAP.md`

These are the foundation, not an end-to-end migration engine. PostgreSQL-to-PostgreSQL snapshot execution, real secret resolution, API, workers, CDC and production reconciliation remain to be implemented.

## Next implementation sequence

1. Wire metadata migrations, CI, settings and secret-provider boundary.
2. Implement PostgreSQL source/target adapters and capability preflight.
3. Implement exported snapshot coordination and bounded key-range readers.
4. Implement streaming COPY and durable chunk recovery.
5. Implement deterministic reconciliation and failure-injection suite.
6. Add PostgreSQL CDC only after snapshot correctness gates pass.
7. Add MySQL and Oracle adapters based on the same contracts.

See [implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md) for exit criteria.
