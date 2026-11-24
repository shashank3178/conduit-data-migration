# Phase 4 — Production-scale execution controls

This phase adds conservative runtime scheduling controls on top of the existing
checkpointed COPY execution pipeline.

## Implemented

- Adaptive per-table writer concurrency. The controller considers local CPU
  capacity, PostgreSQL `max_connections`, observed connections in the current
  database, and a configurable reserved-connection budget.
- Bounded connection lifecycle. A bounded `ThreadPoolExecutor` limits in-flight
  writer tasks; each writer thread reuses its own destination connection, and
  the run closes registered writer connections after each table.
- Partition/batch retry and recovery. Source reads and destination writes retry
  transient operational failures with capped exponential backoff. Checkpoints
  advance in source-primary-key order. A worker crash can replay uncheckpointed
  batches; COPY merge behavior is idempotent under the configured INSERT/UPSERT
  conflict strategy.
- Resource-aware table ordering. Tables with larger discovery row estimates (or
  already measured row counts on resumed runs) are scheduled first to reduce
  the long tail.
- Execution telemetry. Batch events record the selected writer count; analytics
  exposes observed writer concurrency and accumulated table retry counters.
- Run detail UI now includes scheduler, retry, checkpoint, and validation
  strategy information.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `CONDUIT_MIN_WRITERS` | 1 | Minimum writer threads per table |
| `CONDUIT_MAX_WRITERS` | 4 | Maximum writer threads per table |
| `CONDUIT_DB_CONNECTION_RESERVE` | 5 | Connections reserved for application/other workloads |
| `CONDUIT_CPU_WORKER_FACTOR` | 2 | CPU-based upper bound multiplier |

If PostgreSQL connection capacity cannot be inspected, the scheduler falls back
to the minimum writer count rather than risking connection exhaustion.

## Important current limitation

Validation remains a bounded-memory, primary-key-ordered streaming comparison,
but the current orchestration validates tables sequentially after each table's
writes. Parallel validation across independent tables is not implemented in
this phase's current commit set. The UI describes the actual streaming
validation strategy and does not claim parallel validation.

The current table scheduler prioritizes tables; it does not yet run multiple
tables' producers concurrently. Writer concurrency is adaptive within the
active table. This is intentionally conservative because concurrent table
writers need destination lock-contention and per-table checkpoint isolation
tests before being enabled by default.

## Verification

Run from `backend`:

```powershell
ruff check app/services/execution_scheduler.py app/services/migration_execution.py app/api/routes/analytics.py
pytest -q tests/test_execution_scheduler.py tests/test_migration_execution.py
```

Then run a migration with several selected tables and inspect
`/analytics/runs/{run_id}`. The `execution` object reports observed writer
count samples and partition retry counts. Compare these with PostgreSQL
`pg_stat_activity` while the run is active. Do not raise the worker ceiling
until destination connection limits and lock contention have been measured.

No live PostgreSQL load test or frontend build was run while authoring these
changes.
