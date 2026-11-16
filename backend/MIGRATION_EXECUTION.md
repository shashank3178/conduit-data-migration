# Migration execution and reliability

Execution transfers selected, validated plan tables after destination schema preparation. The API queues jobs in metadata PostgreSQL; a separately operated worker claims and executes them.

## Start services

From repository root, start the metadata, source and destination PostgreSQL containers. From backend/, install the project dependencies and apply migrations:

~~~powershell
python -m pip install -e ".[dev]"
alembic upgrade head
~~~

Run the API in one terminal:

~~~powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
~~~

Run one or more durable workers in separate terminals:

~~~powershell
python -m app.worker
~~~

The worker queue uses PostgreSQL row locks (FOR UPDATE SKIP LOCKED); no Redis or Celery service is required. Multiple workers may process different runs concurrently.

## Start a migration

1. Complete source and destination discovery.
2. Create and validate a plan.
3. Apply destination DDL where required.
4. Select a batch size (100–10,000).
5. Select INSERT_ONLY or UPSERT.
6. Queue the migration. A queued run remains queued until a worker claims it.
7. Inspect run, per-table progress, events and row errors.

Example request body:

~~~json
{
  "batch_size": 1000,
  "write_strategy": "UPSERT",
  "max_retries": 3
}
~~~

### Write strategies

- INSERT_ONLY inserts new rows and skips any destination unique-key conflict.
- UPSERT inserts new rows and updates existing rows when mapped non-key values differ. It uses the source primary key as the conflict target and requires the corresponding unique/primary-key constraint on the destination.
- The source is authoritative for UPSERT. This implementation does not merge concurrent writes or synchronize deletes.

All source primary-key columns must be included and mapped. Checkpointed execution requires a primary key and currently supports integer, numeric, UUID, date, timestamp and text-like scalar key types. Unsupported or missing keys fail clearly rather than falling back to unsafe OFFSET paging.

## Reliability model

- Jobs are persisted in migration_runs.
- Workers claim queued jobs using SELECT FOR UPDATE SKIP LOCKED.
- Each table stores a maximum source key and the last committed keyset checkpoint.
- Destination batches commit independently; metadata progress is committed after each destination batch.
- Workers update heartbeats. Stale running jobs are returned to the queue and resumed from the last checkpoint.
- Transient destination connection failures are retried with bounded exponential backoff.
- A failed batch is isolated row by row under savepoints; rejected rows are written to migration_row_errors without storing source payloads.
- Cancellation is cooperative between batches.
- Resume is available for failed/cancelled runs. The retry-errors action replays affected tables from the beginning using the selected idempotent write strategy; prior quarantined row errors are marked resolved when those keys succeed.

Because source and destination are separate PostgreSQL transactions, there is no distributed atomic commit. A worker crash after a destination commit but before metadata checkpoint persistence can replay the last batch. INSERT_ONLY/UPSERT are idempotent for the selected key, but counters may classify replayed rows as skipped rather than preserving the original attempt's insert/update classification.

## Counters and validation

The API persists inserted, updated, skipped and failed row counts at run and table level. For each input row, the expected accounting is:

~~~text
source rows = inserted + updated + skipped + failed
~~~

After each table transfer, a streaming primary-key merge compares mapped source and destination columns. It counts missing, extra and changed rows without loading the entire table into application memory. Validation is marked passed only when there are no mismatches or quarantined rows.

This validation is exact for the mapped columns and primary-key ordering. It scans the source and destination tables and may increase runtime and database load. Existing destination-only rows are reported as extra rows; this is intentional for strict reconciliation.

## API

- POST /api/v1/projects/{project_id}/migration-plans/{plan_id}/runs — queue run
- GET /api/v1/projects/{project_id}/migration-plans/{plan_id}/runs — list runs
- GET .../runs/{run_id} — counters and status
- GET .../runs/{run_id}/tables — per-table progress
- GET .../runs/{run_id}/errors — row-level quarantined failures (up to 5,000)
- POST .../runs/{run_id}/retry-errors — reprocess affected tables and retry quarantined rows
- GET .../runs/{run_id}/events — queue, worker, batch and validation event history
- POST .../runs/{run_id}/resume — resume failed/cancelled run from persisted checkpoint
- POST .../runs/{run_id}/cancel — request cooperative cancellation

## Operational checks

From backend/:

~~~powershell
ruff check app tests
pytest -q
alembic upgrade head
alembic current
alembic heads
~~~

From frontend/:

~~~powershell
npm run lint
npm run build
~~~

Test both strategies, unchanged UPSERT rows, composite primary keys, invalid destination rows, worker termination/restart, cancellation, and exact reconciliation against disposable PostgreSQL databases.

## Limitations

- No distributed transaction spans metadata and destination databases.
- A worker is a separately managed process; deployment must supervise it and keep at least one worker online.
- Retry is bounded for transient connection failures. Quarantined row errors are visible for diagnosis; correct the data/schema issue and start a new idempotent run to retry.
- Foreign-key dependency scheduling, delete synchronization, full schema alteration, and multi-source conflict resolution are not implemented.
