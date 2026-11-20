# Migration observability

## Measurements

Four metadata tables hold run, batch, table and database measurements: `migration_run_metrics`, `migration_batch_metrics`, `migration_table_metrics`, and `migration_database_metrics`.

Logical payload bytes are the UTF-8 size of JSON serialization of fetched row values. They are an application-level payload measure, not TCP/TLS wire bytes. Physical sizes use PostgreSQL `pg_database_size` and `pg_total_relation_size`; snapshots are timestamped and marked exact when the catalog query succeeds.

Existing runs are not backfilled. Missing metrics are returned as null or shown as not collected.

## Checkpoint accounting

Batch metrics use a deterministic SHA-256 identity based on the run-table ID and start/end keyset checkpoints. The metric row, aggregates, counters and checkpoint are committed in the same metadata transaction. Destination writes remain in the existing destination transaction. If destination commit succeeds but metadata commit does not, a replay follows the existing INSERT/UPSERT conflict behavior and only records the batch when the metadata checkpoint advances. This is an idempotent recovery strategy, not a distributed transaction.

The source consistency mode remains a persisted primary-key high-water mark. It does not provide a transactionally consistent source snapshot if source rows change during migration.

## Worker configuration

Optional settings in `backend/.env`:

- `CONDUIT_WORKER_ID`: explicit worker identity; otherwise host/process/random identity is generated.
- `CONDUIT_WORKER_POLL_SECONDS`: queue poll interval (default 2 seconds).
- `CONDUIT_WORKER_HEARTBEAT_SECONDS`: active-run heartbeat interval (default 20 seconds).
- `CONDUIT_WORKER_STALE_SECONDS`: stale-run threshold (default 1800 seconds; minimum 60).

The queue uses PostgreSQL `FOR UPDATE SKIP LOCKED` for atomic job claims. Multiple worker processes may share the same metadata database; keep their total database connections within provider limits.

## Apply and test

From `backend`:

```powershell
python -m pip install -e ".[dev]"
alembic upgrade head
alembic current
ruff check app tests migrations
pytest
```

Run the API and worker in separate terminals:

```powershell
uvicorn app.main:app --reload --port 8000
python -m app.worker
```

From `frontend`:

```powershell
npm ci
npm run lint
npm run build
npm run dev
```

Open `/dashboard/analytics` and `/dashboard/databases`. The analytics page refreshes workspace totals by polling; an individual run detail page uses an authenticated SSE stream through the Next.js proxy. Queue a small PostgreSQL migration and verify run/batch metrics, database size snapshots and table relation sizes. The authenticated analytics and run-event stream endpoints are documented at `/docs`. To inspect the stream directly, use an authenticated HTTP client with `Accept: text/event-stream` against `/api/v1/analytics/runs/{run_id}/stream`; reconnect using the `Last-Event-ID` header.

For multi-worker verification, start a second worker against the same metadata database and queue two independent migrations. Confirm each run records a worker identity and no run is claimed twice.