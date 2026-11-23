# Snowbridge test and benchmark strategy

## Test layers

- **Unit:** canonical schema serialization, type mapping, state transitions, checkpoint guards, key encoding, hash canonicalization, error classification.
- **Adapter contract:** capability reporting, snapshot lifecycle, streaming behavior, cancellation, transactions, replay and idempotency.
- **Integration:** disposable source/target DBs, DDL, COPY/LOAD, sequence sync, CDC ordering.
- **Consistency:** concurrent writes during snapshot; parallel readers share one snapshot; CDC boundary has no gap or duplicate effect.
- **Recovery:** kill worker mid-chunk; restart API; disconnect target during COPY; crash after target commit before metadata checkpoint; replay same CDC transaction; expire lease.
- **Reconciliation:** delete/insert/mutate target rows; composite PK; NULL/decimal/timestamp canonicalization; bucket mismatch deep diff; duplicate detection.
- **Security:** secret redaction, tenant isolation, least privilege, TLS configuration and temp-file cleanup.
- **Scale:** narrow, wide, LOB, skewed, composite/no PK, partitioned, FK-heavy and high-write tables.

## Failure injection

1. Kill reader and writer at each transaction boundary.
2. Commit target data then force metadata failure.
3. Disconnect source during snapshot and CDC.
4. Fill target disk and saturate connection pools.
5. Expire PostgreSQL logical slot retention / remove MySQL binlog history / simulate Oracle redo gap.
6. Alter DDL while migration is active.
7. Inject invalid decimal, zero date, timezone edge, oversized LOB and constraint violation.
8. Delete, mutate and insert destination rows before reconciliation.

## Benchmark profiles

Run representative 1 GB, 10 GB, 100 GB, 500 GB and 1 TB+ profiles where infrastructure allows. Include uniform and skewed distributions, wide rows, LOBs and concurrent source writes. Report actual data shape and hardware; these sizes are test targets, not performance claims.

Measure committed GB/s, rows/s, source read and target commit latency, CPU, memory peak, network, connection count, CDC lag, retry/DLQ rate, reconciliation cost and recovery time. Separate source extraction, network transfer, target commit and end-to-end throughput.

## Acceptance gates

- Memory remains bounded as table size increases.
- No data loss or duplicate logical effects after injected restarts.
- Independent chunk recovery without restarting the whole migration.
- Checkpoint never advances before target commit.
- Snapshot/CDC boundary is gap-free.
- Reconciliation is deterministic and produces actionable row/range diagnostics.
- Throughput improves under added concurrency only while resource limits remain safe.
- No silent lossy conversion or hidden row rejection.
