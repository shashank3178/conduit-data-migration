# CONDUIT — Enterprise Data Migration Platform

CONDUIT is a PostgreSQL-to-PostgreSQL migration workbench using Next.js 15, React 19, Tailwind, FastAPI, SQLAlchemy, Psycopg 3, and PostgreSQL. Its workflow is **data connections → discovery → migration planning → destination schema preparation → batch execution**.

> Implemented: authenticated projects, Fernet-encrypted database credentials, catalog discovery, table/column mapping, plan validation, safe DDL, batch data transfer, run telemetry, and cooperative cancellation. Migration execution is queued in metadata PostgreSQL and processed by a separately operated worker. Phase 6 adds INSERT_ONLY/UPSERT, primary-key keyset checkpoints, retry, row-error quarantine, exact streaming reconciliation, and execution event history.

## Architecture

~~~text
Browser (Next.js) → Auth0 session/server actions → FastAPI /api/v1 (JWT RS256/JWKS)
                                                 ├─ Metadata PostgreSQL
                                                 ├─ Source PostgreSQL (read/extract)
                                                 └─ Destination PostgreSQL (DDL + batch insert)
~~~

| Service | Local address |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Metadata DB | localhost:5433 |
| Sample source DB | localhost:5434 |
| Sample destination DB | localhost:5435 |

## How the migration works (implementation)

1. **Connections:** backend/app/services/connection_service.py encrypts passwords with Fernet before persistence. Passwords/ciphertext aren't returned by API response schemas.
2. **Discovery:** backend/app/services/discovery_service.py uses SQLAlchemy Inspector and PostgreSQL catalog queries; stores schemas, relations, columns, PK/FK, constraints, indexes, comments, and estimated row counts as metadata snapshots. It never transfers rows.
3. **Plan:** backend/app/services/migration_plan_service.py:create_plan() reads completed snapshots, pairs destination tables by exact schema+table name, creates plan table candidates and per-column mappings.
4. **Column mapping:** _suggest_column_mappings() uses exact column-name matches for existing target tables; unmatched source columns are excluded/unmapped. New target tables get same-name/same-type suggestions. This is deterministic rules + manual overrides, not AI/fuzzy mapping.
5. **Type checks:** backend/app/services/migration_ddl.py:types_compatible() supports normalized type equality and conservative widening (integer/floating ranks and VARCHAR length). It does not guess arbitrary casts.
6. **DDL:** build_ddl() quotes identifiers and restricts types to an allow-list. Applying DDL creates missing schemas/tables only; it does not drop, truncate, or alter existing tables.
7. **Execution:** backend/app/services/migration_execution.py uses primary-key keyset pagination, parameterized multi-row inserts, INSERT_ONLY conflict skipping, and UPSERT updates for changed non-key columns. Source primary keys must be mapped; UPSERT also requires a matching destination unique/primary-key constraint.
8. **Durable jobs:** API requests enqueue MigrationRun records. One or more separate worker processes claim jobs with PostgreSQL FOR UPDATE SKIP LOCKED. Batch checkpoints and worker heartbeats are stored in metadata PostgreSQL.
9. **Accounting and validation:** per-run/per-table inserted, updated, skipped, failed and mismatch counters are persisted. Row-level write failures are quarantined; mapped values are compared in a streaming primary-key merge after transfer. Run events record queue, worker, batch and validation activity.

## Local setup (Windows PowerShell)

Prerequisites: Git, Python 3.11+, Node.js 20+ LTS, Docker Desktop/Compose, and an Auth0 application/API.

### 1. Clone and configure
~~~powershell
git clone https://github.com/shashank3178/conduit-data-migration.git
cd conduit-data-migration
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.local.example frontend/.env.local
~~~
Edit backend/.env:
- DATABASE_URL=postgresql+psycopg://conduit:conduit@localhost:5433/conduit_metadata
- AUTH0_DOMAIN (tenant domain without scheme)
- AUTH0_ISSUER (exact issuer URL including trailing slash)
- AUTH0_AUDIENCE=https://api.conduit.local
- CONNECTION_ENCRYPTION_KEY (stable Fernet key)

Generate Fernet key:
~~~powershell
cd backend
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
cd ..
~~~
Edit frontend/.env.local with your Auth0 client ID/secret and a new random AUTH0_SECRET. Never commit real secrets.

### 2. Start PostgreSQL
From repo root:
~~~powershell
docker compose up -d metadata-db
docker compose -f docker-compose.databases.yml up -d
docker compose ps
~~~
Ports: metadata 5433, source 5434, destination 5435. Source seed is database-seed/source/01-init.sql (first volume initialization).

### 3. Install backend and migrate metadata schema
~~~powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
alembic upgrade head
alembic current
alembic heads
~~~
Expected revision: **f6a1b2c3d4e5**.

### 4. Install frontend
In another terminal:
~~~powershell
cd conduit-data-migration\frontend
npm ci
~~~

## Run the app locally

**Terminal 1 — backend:**
~~~powershell
cd conduit-data-migration\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
~~~

**Terminal 2 — migration worker:**
~~~powershell
cd conduit-data-migration\backend
.\\.venv\Scripts\Activate.ps1
python -m app.worker
~~~
Keep at least one worker running; multiple worker processes may share the PostgreSQL-backed queue.

**Terminal 3 — frontend:**
~~~powershell
cd conduit-data-migration\frontend
npm run dev
~~~

Visit http://localhost:3000 and sign in with Auth0. Open Dashboard → Migration planning. Swagger: http://localhost:8000/docs.

## Test a sample migration

1. Create a project.
2. Source connection: localhost:5434, database source_db, user source_user, password source_pass_123.
3. Destination connection: localhost:5435, database destination_db, user destination_user, password destination_pass_123.
4. Test connections and run discovery on both.
5. Create plan; select regular tables; review/edit mappings; save and validate.
6. Preview destination DDL and apply it.
7. Start migration, choose batch size, refresh status, inspect per-table progress.
8. Verify destination using SQL client:
~~~sql
SELECT COUNT(*) FROM public.customers;
SELECT * FROM public.customers LIMIT 10;
~~~
Use actual selected table/schema names. Sample credentials are local Docker-only.

## API/authentication

Protected APIs use Auth0 access tokens for audience https://api.conduit.local. FastAPI validates RS256/JWKS signature, issuer, and audience. Next.js server actions obtain tokens and forward them; tokens are not passed into client components.

- /users/me and /projects
- /projects/{project_id}/connections (CRUD/test)
- /projects/{project_id}/connections/{connection_id}/discover and /discovery
- /projects/{project_id}/migration-plans (plan, selection, mapping, validation, DDL)
- /projects/{project_id}/migration-plans/{plan_id}/runs (queue/list/status/table progress/cancel/resume)
- /projects/{project_id}/migration-plans/{plan_id}/runs/{run_id}/errors (row-level rejects) and /retry-errors (retry quarantined rows)
- /projects/{project_id}/migration-plans/{plan_id}/runs/{run_id}/events (audit/telemetry)
- /projects/{project_id}/migration-plans/{plan_id}/runs/{run_id}/report and /report.csv (JSON/CSV exports)

Swagger Authorize: Bearer <access-token>. Do not paste real tokens into chat, source, commits, or logs.

## Code map

| Concern | Source |
|---|---|
| JWT and project ownership | backend/app/api/dependencies.py |
| Settings/DB session | backend/app/core/config.py; backend/app/db/session.py |
| Connection encryption/test | backend/app/services/connection_service.py |
| Catalog discovery | backend/app/services/discovery_service.py |
| Plan/mapping/validation | backend/app/services/migration_plan_service.py |
| Type allow-list and DDL | backend/app/services/migration_ddl.py |
| Batch execution, UPSERT and reconciliation | backend/app/services/migration_execution.py |
| Durable worker | backend/app/worker.py |
| Run/checkpoint/error/event models | backend/app/models/migration_run.py; backend/migrations/versions/f6a1b2c3d4e5_phase6_reliability.py |
| Plan/run APIs | backend/app/api/routes/migration_plans.py; migration_runs.py |
| Run models/revision | backend/app/models/migration_run.py; backend/migrations/versions/c81f3a9d2e40_add_migration_execution.py |
| Planning/execution UI | frontend/src/app/dashboard/migration-planning/planning-client.tsx; execution-panel.tsx |

## Checks

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

Automated backend tests cover discovery serialization, DDL generation, checkpoint key serialization, and write-outcome accounting. Run the complete suite and exercise UPSERT, worker restart, row rejects, and reconciliation against disposable PostgreSQL databases before production use.

## Safety and limitations

- A worker crash after a destination commit but before metadata checkpoint commit can replay the last batch. INSERT_ONLY and UPSERT are idempotent for the configured conflict key, but cross-database atomic commits are not provided; aggregate counters after an ambiguous crash need reconciliation.
- Keyset checkpointing currently requires a mapped primary key and supported scalar key types. Tables without primary keys are rejected rather than migrated with unsafe OFFSET pagination.
- UPSERT is source-authoritative and requires a matching destination unique/primary-key constraint. It does not synchronize deletes or resolve concurrent writes from two authoritative systems.
- Transient connection failures are retried; row-level constraint/conversion failures are quarantined. Correct the underlying issue and start a new idempotent run to retry rejected rows.
- Validation compares mapped columns and keys exactly. It is streaming, but a full table scan can add substantial runtime and database load.
- Foreign-key dependency scheduling, delete synchronization, schema alteration, and cross-database distributed transactions remain outside this implementation.
- Existing destination tables are never dropped/truncated/altered; ensure compatible shape.
- Back up data, use least privilege and SSL for remote databases, and never log secrets or sensitive row payloads.

## Step guides
- [Data connections](backend/DATA_CONNECTIONS.md)
- [Data discovery](backend/DATA_DISCOVERY.md)
- [Migration planning](backend/MIGRATION_PLANNING.md)
- [Migration execution](backend/MIGRATION_EXECUTION.md)

Documentation uses product step/domain names rather than historical phase numbers.


## Migration observability

Discovery captures PostgreSQL database size plus per-table total, heap/TOAST, and index storage using PostgreSQL catalog size functions. These are point-in-time storage measurements; row estimates remain estimates until execution obtains exact table counts.

Each committed worker batch persists its record count, inserted/updated/skipped/failed outcomes, UTF-8 JSON payload-size estimate, committed payload estimate, duration, and throughput. Payload measurements exclude PostgreSQL wire-protocol overhead and are intentionally distinguished from physical source/destination storage.

The authenticated run APIs expose `/batches` and `/metrics`. The frontend provides:
- `/dashboard/runs` — auto-refreshing registry of runs across projects.
- `/dashboard/runs/{run_id}?projectId=...&planId=...` — durable run-specific monitor with row, byte, table, batch, throughput, and event metrics.

A run continues in the backend worker when the user navigates away or reloads the browser. Run state and telemetry are persisted in metadata PostgreSQL. Apply the new Alembic revision with `alembic upgrade head`.

The batch payload size is an application-level JSON serialization estimate, not exact PostgreSQL network traffic. Committed payload is apportioned from the batch estimate using inserted and updated row counts; ambiguous cross-database commit outcomes still require final reconciliation.
