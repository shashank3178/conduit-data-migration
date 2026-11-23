# Conduit V2 — Architecture Reset

## Objective

Rebuild the application around a production-oriented, database-agnostic migration platform. V2 is not a refactor of V1's execution path.

## Explicitly removed from this branch

The V2 working tree intentionally does not contain the V1 application source, migration engines, migration execution pipeline, or validation mechanism. Those files remain available on `main` and in V1 history. This reset is branch-scoped; it does not delete or rewrite V1.

## Design principles

1. **Independent V2 implementation:** no imports, runtime dependencies, or shared deployment artifacts from V1.
2. **Metadata-driven planning:** inspect source and target capabilities before execution; represent decisions in an explicit migration plan.
3. **Capability-based adapters:** isolate vendor-specific discovery, DDL, bulk load, transaction, and type-mapping behavior behind adapter contracts.
4. **Resumable execution:** durable checkpoints, idempotent task boundaries, bounded concurrency, and explicit retry semantics.
5. **Observable by default:** structured run events, per-object progress, throughput, resource metrics, and actionable failure diagnostics.
6. **Correctness as a first-class contract:** define reconciliation and consistency semantics before implementing a new validation subsystem.
7. **Large-database readiness:** streaming metadata and data paths, backpressure, bounded memory, and no table-size-proportional buffering.
8. **Security:** secrets are references to managed credentials, never persisted in plaintext or emitted in logs.

## Proposed implementation sequence

- [ ] Architecture decision records and domain model
- [ ] Database adapter contracts and capability negotiation
- [ ] Connection and credential lifecycle
- [ ] Metadata discovery and schema inventory
- [ ] Type mapping and DDL planning
- [ ] Durable orchestration and checkpoint model
- [ ] Bulk data plane and adaptive backpressure
- [ ] Reconciliation design and correctness test strategy
- [ ] Run observability, diagnostics, and operator workflows
- [ ] UI rebuilt against versioned V2 APIs
- [ ] Integration, scale, failure-injection, and recovery tests

## Non-goals for the reset commit

This commit does not introduce a replacement engine, pretend validation implementation, or placeholder production code. Each subsystem will be designed and implemented against explicit contracts in subsequent V2 commits.
