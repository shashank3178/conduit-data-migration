# CONDUIT — Enterprise Data Migration Platform

CONDUIT is a PostgreSQL-to-PostgreSQL migration workbench using Next.js 15, React 19, Tailwind, FastAPI, SQLAlchemy, Psycopg 3, and PostgreSQL. Its workflow is **data connections → discovery → migration planning → destination schema preparation → batch execution**.

> Implemented: authenticated projects, Fernet-encrypted database credentials, catalog discovery, table/column mapping, plan validation, safe DDL, batch data transfer, run telemetry, and cooperative cancellation. The current runner is a FastAPI in-process background task for local/prototype use; production requires a durable worker/queue.

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
7. **Execution:** backend/app/services/migration_execution.py:execute_run() opens Psycopg connections, reads via named/server-side cursors in fetchmany(batch_size), applies saved mappings, parameterizes values, and commits destination batches independently. ON CONFLICT DO NOTHING skips duplicate-key conflicts.
8. **Progress:** MigrationRun and MigrationRunTable persist statuses, row counts, table progress, and errors. Cancellation is checked between batches.

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
Expected revision: **c81f3a9d2e40**.

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

**Terminal 2 — frontend:**
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
- /projects/{project_id}/migration-plans/{plan_id}/runs (start/list/status/table progress/cancel)

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
| Batch execution | backend/app/services/migration_execution.py |
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

Automated backend tests currently cover discovery serialization and DDL generation. Validate row transfer against disposable databases before production use.

## Safety and limitations

- BackgroundTasks is process-local/not durable; restart can interrupt a run. Production needs a dedicated durable worker/queue.
- Destination batches commit independently; failure can leave earlier batches committed. Full checkpoint/resume is not implemented.
- ON CONFLICT DO NOTHING is duplicate-key skip, not upsert/reconciliation.
- FK dependency ordering, row-level reject quarantine, resumable checkpoints, checksums, and complete constraint/index/identity cloning remain future work.
- Existing destination tables are never dropped/truncated/altered; ensure compatible shape.
- Back up data, use least privilege and SSL for remote databases, and never log secrets or sensitive row payloads.

## Step guides
- [Data connections](backend/DATA_CONNECTIONS.md)
- [Data discovery](backend/DATA_DISCOVERY.md)
- [Migration planning](backend/MIGRATION_PLANNING.md)
- [Migration execution](backend/MIGRATION_EXECUTION.md)

Documentation uses product step/domain names rather than historical phase numbers.
