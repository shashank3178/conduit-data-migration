# Migration execution profiling (Phase 1)

Phase 1 adds low-overhead profiling to the existing migration worker. It does not change the migration data path or checkpoint semantics.

## Where the measurements are stored

The worker writes the measurements into the existing `migration_run_events` JSONB event stream. No schema migration is required.

For a run ID:

```sql
SELECT
    created_at,
    event_type,
    details
FROM migration_run_events
WHERE run_id = '<RUN_ID>'
  AND event_type IN ('batch_committed', 'run_finished', 'run_failed')
ORDER BY created_at;
```

### Per-batch fields (`batch_committed`)

- `source_fetch_duration_ms`: time spent fetching the source batch.
- `destination_write_duration_ms`: time spent in destination COPY/staging/merge.
- `duration_ms`: batch processing wall time before metadata commit.
- `batch_cpu_ms`: process CPU time consumed while processing the batch.
- `logical_bytes`: estimated logical payload size (JSON representation), not wire bytes.
- `process_peak_rss_bytes`: best-effort process peak resident memory.

### Run summary fields (`run_finished` / `run_failed`)

- `wall_clock_elapsed_ms`: end-to-end worker elapsed time, including validation and coordination.
- `process_cpu_ms`: process CPU time over the run.
- `batch_metadata_commit_total_ms`: cumulative time spent committing batch checkpoint/metric transactions.
- `logical_throughput_bytes_per_second`: logical payload bytes divided by end-to-end wall time.
- `process_peak_rss_bytes`: best-effort process peak resident memory.

On Windows, peak RSS is read through the Windows process API. On Linux/macOS it uses the standard `resource` module.

## Interpreting a slow run

- High `source_fetch_duration_ms`: source query latency, source load, network RTT, or keyset/index inefficiency.
- High `destination_write_duration_ms`: destination network, COPY, indexes, constraints, or staging merge.
- High `batch_cpu_ms` relative to `duration_ms`: Python-side adaptation/serialization or other CPU work.
- High `batch_metadata_commit_total_ms`: metadata database latency or excessive checkpoint frequency.
- High wall time but low summed batch duration: validation, connection setup, snapshots, retries, or coordination dominate.

## Measurement limitation

The current driver does not expose reliable socket-level bytes transferred for each PostgreSQL connection. Therefore `logical_bytes` and `logical_throughput_bytes_per_second` are application-payload estimates, not physical network throughput. Network RTT is also latency, not bandwidth. Do not present either value as measured wire throughput.
