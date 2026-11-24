# Phase 3: PostgreSQL data-path optimization

## Changes

- Reuse each destination writer thread's PostgreSQL connection. The temporary staging table is now actually reused across batches on that connection instead of being recreated with every batch connection.
- Keep text COPY as the default. `CONDUIT_COPY_FORMAT=binary` opts into PostgreSQL binary COPY for benchmark/compatibility testing.
- Replace per-row `RETURNING` result transfer to Python with server-side aggregate counts in a data-modifying CTE.
- Remove the redundant post-merge staging-table TRUNCATE. The next batch truncates the stage before loading.
- Replace JSON serialization in the normal logical-byte metric path with a lightweight value-size estimate. Set `CONDUIT_EXACT_LOGICAL_BYTES=1` to restore the slower legacy JSON measurement.
- Remove the per-batch `MAX(sequence)` query. The table metric's ordered batch counter supplies the next sequence.
- Avoid committing an otherwise clean writer metadata session.
- Persist the coordinator's checkpoint/metrics transaction every four batches by default, configurable with `CONDUIT_METADATA_COMMIT_EVERY` (1-16). The final partial group is committed before validation.

## Configuration

Recommended starting point:

```env
CONDUIT_WRITE_ENGINE=COPY
CONDUIT_COPY_FORMAT=text
CONDUIT_MIGRATION_WRITERS=2
CONDUIT_METADATA_COMMIT_EVERY=4
CONDUIT_EXACT_LOGICAL_BYTES=0
CONDUIT_COPY_SYNCHRONOUS_COMMIT=on
```

Do not turn on binary COPY until the benchmark and a representative end-to-end migration confirm compatibility and a real speedup:

```env
CONDUIT_COPY_FORMAT=binary
```

Binary COPY can be faster for supported PostgreSQL/Psycopg type adapters, but it applies no implicit casts. The implementation sets explicit destination types for common scalar types and rejects unsupported types such as arrays and user-defined domains. Text remains the safe default.

## Benchmark text vs binary COPY

Use a disposable PostgreSQL database, not a production destination:

```powershell
cd backend
$env:CONDUIT_BENCHMARK_DSN = "postgresql://user:password@host:5432/disposable_db?sslmode=require"
python scripts/benchmark_copy_formats.py --rows 100000 --repeats 3
```

The benchmark writes the same BIGINT/TEXT dataset through text and binary row-wise COPY on the same connection, explicitly sets the binary types to BIGINT/TEXT, verifies row counts, and reports median rows/s and estimated MB/s. It isolates COPY ingest; it does not include staging merge, indexes, constraints, network source extraction, or validation. Repeat against the actual destination network/database class before choosing a format.

## Checkpoint commit frequency and recovery

The metadata checkpoint and batch metrics are committed together every N batches. Destination batch writes still commit individually. If the worker crashes before the metadata group commit, up to N-1 already-written batches may be replayed. This relies on the existing idempotent INSERT-ONLY (`ON CONFLICT DO NOTHING`) and UPSERT behavior. Set `CONDUIT_METADATA_COMMIT_EVERY=1` for per-batch metadata durability / the most conservative recovery window; use 2-4 for a reasonable throughput trade-off. Do not use a non-idempotent write strategy with grouped checkpoints.

## Destination durability tuning

`CONDUIT_COPY_SYNCHRONOUS_COMMIT=off` opts into transaction-local `synchronous_commit=off` for COPY batches. This can reduce commit latency on a destination whose measured bottleneck is WAL flush latency, but acknowledged recent commits can be lost after a database/OS crash. It is therefore OFF by default and is not recommended for production migrations where acknowledged-batch durability is required. Use only on a disposable/test destination or with explicit acceptance of that durability trade-off.

Before changing destination settings, inspect the destination:

```sql
SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN (
  'synchronous_commit', 'wal_compression', 'max_wal_size',
  'checkpoint_timeout', 'shared_buffers', 'work_mem',
  'maintenance_work_mem', 'max_connections'
)
ORDER BY name;

SELECT
  checkpoints_timed, checkpoints_req,
  buffers_checkpoint, buffers_clean, buffers_backend,
  checkpoint_write_time, checkpoint_sync_time,
  wal_bytes, wal_buffers_full
FROM pg_stat_bgwriter
CROSS JOIN LATERAL (SELECT wal_bytes FROM pg_stat_wal) wal;
```

Tune server-level WAL/checkpoint/memory settings with the DBA based on those measurements; this application does not silently change global PostgreSQL settings.

## Metric interpretation

Logical payload bytes are now an inexpensive estimate, not the exact legacy JSON byte count and not wire bytes. For exact comparisons only, set `CONDUIT_EXACT_LOGICAL_BYTES=1` for both benchmark runs. Do not compare estimated logical throughput against historical exact-JSON throughput as if the metric definition were unchanged.

## Validation checklist

1. Run backend tests and Ruff.
2. Run the text-vs-binary benchmark on a disposable database.
3. Run a representative migration with default text COPY and compare Phase 1 stage timings.
4. Repeat with binary COPY only if the benchmark shows a repeatable improvement.
5. Verify inserted/updated/skipped counts, row errors, final validation, and restart/replay behavior.
6. Compare destination physical size and WAL/checkpoint statistics before attempting server tuning.
