# Streaming COPY performance path

## What changed

The normal migration writer now uses PostgreSQL's COPY protocol to load each bounded
application batch into a reusable temporary staging relation. It then performs one
set-based INSERT/UPSERT from staging into the destination table.

This replaces the previous large parameterized VALUES statement for real Psycopg
connections. It reduces per-row adaptation/parameter overhead and avoids rebuilding
a multi-thousand-placeholder SQL statement for every batch.

The staging table is scoped to the destination connection and destination table.
It is created with `ON COMMIT PRESERVE ROWS`, truncated before and after each
batch, and reused by subsequent batches. The existing transaction boundary remains
responsible for atomicity: staging load, merge, and the caller's checkpoint commit
must succeed together.

## Rollback switch

Set the backend worker environment variable:

```env
CONDUIT_WRITE_ENGINE=VALUES
```

The default is `COPY`. The VALUES path remains available for diagnosis and for
database roles where COPY privileges are intentionally unavailable. A PostgreSQL
role needs the ordinary table privileges required by the target operation; COPY
FROM STDIN does not require the server-side file privilege.

Restart every migration worker after changing this setting.

## Operational constraints

- Keep one persistent destination connection per executing worker; temporary
  staging relations are connection-local.
- Do not share a Psycopg connection concurrently between worker threads.
- Batch commit and checkpoint ordering must remain unchanged.
- The destination still needs sufficient WAL, disk I/O, index-maintenance, and
  connection capacity. COPY cannot overcome a saturated destination.
- The writer preserves INSERT_ONLY conflict skipping and UPSERT changed-row
  semantics. Invalid data continues through the existing recursive batch
  isolation path, which records the rejected source key and PostgreSQL error.
- This optimization does not make a mapped migration equivalent to a full
  PostgreSQL clone. Use a native dump/restore engine only after compatibility,
  destination-state, schema, extension, and transformation constraints have
  been checked.

## Verification

Run from `backend/`:

```bash
python -m pytest
ruff check .
```

Then run a UI migration against a disposable PostgreSQL source and destination.
Compare the same dataset using the default COPY path and the rollback VALUES path.
Check final validation, INSERT_ONLY conflict behavior, UPSERT behavior, row-level
error isolation, worker restart recovery, and cancellation.

Measure sustained end-to-end throughput over a sufficiently large dataset.
Report logical bytes transferred divided by elapsed migration time; do not infer
network throughput from destination table size or from the speed of COPY alone.
The 10 MB/s target is an acceptance target, not a guaranteed result until measured
on the actual source, destination, worker, and network.
