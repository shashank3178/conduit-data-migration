# Snowbridge implementation roadmap

## Milestone 0 — Foundation (this commit)

- [x] Product identity and V2 branch boundary documented
- [x] Architecture decision records
- [x] Canonical domain and adapter contracts
- [x] Initial metadata schema
- [x] Contract tests for lifecycle/checkpoint invariants
- [ ] CI and database migration tooling wired into repository
- [ ] Secret-provider implementation and API skeleton

## Milestone 1 — PostgreSQL → PostgreSQL snapshot vertical slice

1. Connection registry and runtime secret resolution.
2. PostgreSQL source/target adapters with version and privilege preflight.
3. Streaming catalog discovery and canonical schema IR.
4. Conservative DDL planner with explicit unsupported mappings.
5. Exported snapshot coordinator and parallel snapshot import.
6. Keyset/range chunk planner with row and byte ceilings.
7. Streaming COPY FROM STDIN target writer.
8. Atomic chunk commit and durable checkpoint recovery.
9. Counts/bounds and canonical bucket reconciliation.
10. Structured run events, throughput and resource telemetry.

**Exit gates:** concurrent source writes do not create a fractured snapshot; worker/API restart recovers; target commit/checkpoint gap is replay-safe; no whole-table buffering; row/byte budgets are respected; data diff is empty; benchmark suite passes.

## Milestone 2 — CDC for PostgreSQL

Logical decoding capability preflight, publication/slot lifecycle, LSN checkpointing, transaction ordering, retention pressure controls, replay-safe target apply and DDL drift policy.

## Milestone 3 — MySQL adapters

InnoDB consistent snapshot coordinated with GTID/binlog boundary, indexed key ranges, row-based binlog capture, LOAD DATA/staging and type-semantic handling.

## Milestone 4 — Oracle adapters

SCN-consistent reads, approved LogMiner/XStream capture strategy, ROWID/key chunking, array binds/direct-path load, LOB streaming and NUMBER/DATE/empty-string semantics. Licensing and permissions are preflight gates.

## Milestone 5 — Reconciliation, cutover and production hardening

Deep PK diff/repair, durable DLQ, cutover gate, rollback strategy, multi-tenant RBAC, audit, secret rotation, telemetry, chaos/recovery and scale benchmarks.

## Pairing sequence

PostgreSQL→PostgreSQL; MySQL→PostgreSQL; PostgreSQL→MySQL; MySQL→MySQL; Oracle→PostgreSQL; PostgreSQL→Oracle; then additional pairs based on customer demand. Implement adapters and capabilities, not a separate engine per pair.
