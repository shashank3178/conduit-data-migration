# Snowbridge architecture

## System boundaries

```text
                  MANAGEMENT PLANE
 UI / API ── Projects · Connections · Inventory · Plans · Policy
                    │ durable commands
                    ▼
              ORCHESTRATOR
      Runs · Tasks · Leases · Checkpoints · Retry
                    │ schedules bounded work
                    ▼
                    DATA PLANE
 Source Adapter → Snapshot / CDC → Transform → Target Adapter
                         │                         │
                         └──── telemetry ─────────┘
                                  ▼
                      Reconciliation / Cutover
                                  │
                    Metadata PostgreSQL + OTel
```

The management plane must never proxy bulk table contents. Workers connect directly to source and target through adapter APIs. Metadata stores control-plane state, not row payloads or high-frequency metric samples.

## Implemented PostgreSQL primitives

The initial adapter uses Psycopg 3 and provides:
- connectivity and capability inspection;
- catalog discovery for ordinary and partitioned tables, columns and primary/unique keys;
- an exported repeatable-read snapshot keeper;
- a worker snapshot-import operation;
- a composite-key keyset page reader;
- a streaming COPY FROM STDIN row writer.

These are building blocks, not a complete run executor. The current keyset reader bounds rows per page but does not yet enforce a hard serialized-byte ceiling or stream LOB values independently. The snapshot keeper must remain open until every worker has imported the snapshot. The source read transaction must stay on the same imported snapshot for all pages.

The metadata migration runner applies numbered SQL files under a PostgreSQL advisory transaction lock and records SHA-256 checksums. Editing an already-applied migration is rejected; create a new numbered migration instead.

## Core subsystems

1. **Connection and secret boundary** — encrypted transport, secret references, least-privilege checks, connectivity and capability preflight.
2. **Discovery and planning** — streaming catalog inspection; canonical schema IR; explicit type mapping classifications and operator decisions.
3. **Adapter registry** — source and target contracts are separate. A database can support extraction but not CDC, or bulk loading but not a specific transactional mode.
4. **Snapshot engine** — consistent snapshot boundary, key-range chunking, bounded readers, byte-based limits, streaming rows.
5. **CDC engine** — source-log positions (LSN, GTID/binlog position, SCN), transaction boundaries, ordering and durable capture.
6. **Bulk load and apply** — native target loading, optional staging, replay-safe upsert/delete handling.
7. **Reconciliation** — schema parity, range counts, canonical bucket hashes, deep PK diff and repair workflow.
8. **Orchestration** — durable state machine, task leases, retries, cancellation and recovery.
9. **Observability** — structured events, per-table throughput, bytes, lag, resource pressure and actionable errors.

## Consistency boundary

A snapshot and CDC start position must be coordinated by the source adapter. Parallel readers must share the same logical snapshot (PostgreSQL exported snapshot, MySQL consistent snapshot/binlog coordinate, Oracle SCN/flashback). Starting CDC only after snapshot completion can lose writes that occur during extraction.

## Execution guarantees

The cross-database default is **at-least-once delivery with idempotent target application**. A target commit can succeed while metadata checkpoint persistence fails. The worker must safely replay that unit using a stable task/batch identity and a target-side idempotency strategy. Do not describe this as distributed exactly-once.

A checkpoint is advanced only after target commit confirmation and durable metadata persistence. Ambiguous outcomes must be replayed safely or reconciled, never skipped.

## Large database constraints

- Stream rows; never fetch an entire table into Python memory.
- Bound both rows and serialized bytes per chunk.
- Use keyset/range scans over suitable keys; do not use OFFSET for large tables.
- Isolate very wide rows and LOBs from ordinary batches.
- Apply backpressure based on source/target CPU, I/O, pool saturation, lock waits, memory, CDC lag and log-retention pressure.
- Limit concurrency per source and target, not just globally.
- Treat benchmark batch sizes as starting hypotheses, not constants.

## Database-specific strategy

| Engine | Snapshot | CDC position | Bulk target |
|---|---|---|---|
| PostgreSQL | exported MVCC snapshot; keyset/range | logical decoding LSN | COPY FROM STDIN |
| MySQL/InnoDB | consistent snapshot; indexed key ranges | GTID or binlog file/position | LOAD DATA / batched writes |
| Oracle | common SCN / flashback; ROWID or key ranges | SCN via approved capture | array binds / direct path |

Capability and permission requirements are version-specific and must be probed during preflight.
