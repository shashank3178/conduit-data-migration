# Migration execution

Execution transfers selected, validated plan tables after destination schema preparation.

## Workflow
1. Validate plan and apply destination DDL.
2. Open the Run migration panel.
3. Choose batch size (100–10,000) and start.
4. Review run status, inserted row count, completed tables, per-table progress/errors.
5. Request cancellation if needed; cancellation is cooperative between batches.
6. Independently verify destination counts and application invariants.

## API
- POST /api/v1/projects/{project_id}/migration-plans/{plan_id}/runs body {"batch_size":1000} — create/start
- GET .../runs — list
- GET .../runs/{run_id} — counters/status
- GET .../runs/{run_id}/tables — table progress
- POST .../runs/{run_id}/cancel — cancellation request

## Implementation
- app/services/migration_execution.py:execute_run() loads persisted plan/connection records and decrypts credentials only when connecting.
- A named Psycopg cursor reads bounded fetchmany(batch_size) batches rather than loading a full table.
- Included saved mappings determine source and destination column order. Psycopg SQL composition quotes identifiers; row values are parameterized.
- Destination executemany inserts batches; each batch commits separately. ON CONFLICT DO NOTHING skips duplicate key conflicts.
- MigrationRun and MigrationRunTable persist statuses/counters. Authenticated APIs enforce project/plan ownership.

## Limitations
The runner uses FastAPI BackgroundTasks in the same process and is prototype/local only. Restart can interrupt work. Earlier committed batches remain after later failures. Full checkpoint/resume, row-level quarantine/retry, FK ordering, upsert/reconciliation, checksum validation, and a durable queue/worker are not implemented. Do not use on production data without backups and a recovery plan.
