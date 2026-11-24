# Snowbridge — Enterprise Database Migration Platform

Snowbridge is a V2 database migration platform. All V2 work is isolated on `v2/rebuild`; V1 `main` remains untouched.

## Current runnable demonstration

This branch now includes:
- PostgreSQL, MySQL and Oracle connection/discovery adapters and common inventory contracts.
- A FastAPI backend for connection testing, PostgreSQL schema discovery, and a PostgreSQL-to-PostgreSQL snapshot migration.
- A Next.js control-plane UI for connection configuration, discovery, catalog estimates, capability display, and migration progress.
- A consistent PostgreSQL exported MVCC snapshot, target DDL preparation, bounded binary COPY streaming, and target-side replay ledger for per-table commits.
- Existing metadata schema, lease/checkpoint primitives, adaptive integer chunk planning and unit/integration tests.

**Important scope boundary:** the executable API pipeline is PostgreSQL-to-PostgreSQL only and snapshot-only. It requires matching PostgreSQL major versions and empty target tables. It refuses to truncate or append into non-empty target tables. MySQL/Oracle are currently discovery/capability adapters, not executable migration sources or targets. CDC, automatic reconciliation, durable API job state, authentication/RBAC and cutover are not complete. The API's demo job state is in memory and is lost when the process restarts. Do not expose this demo API directly to the public internet or use it for production data.

## Run backend

Python 3.11+ recommended.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[discovery]"
Copy-Item .env.example .env
# Configure SNOWBRIDGE_METADATA_DATABASE_URL in .env if using metadata migrations
python -m snowbridge
```

API docs: http://127.0.0.1:8000/docs

Health: http://127.0.0.1:8000/api/health

The demo API does not require the metadata database to start. The metadata migration command remains available separately:
```powershell
python -m snowbridge.metadata.migrate
```

## Run frontend

Open a second terminal:
```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000.

## Demo workflow

1. Configure a source PostgreSQL endpoint and test it.
2. Configure a distinct target PostgreSQL endpoint.
3. Optionally enter comma-separated source schemas (blank means all accessible schemas).
4. Select **Discover schema** to view table inventory, approximate rows/bytes and source capabilities.
5. Select **Run snapshot migration**. The target must be empty for every discovered table. The pipeline prepares conservative target DDL, exports one consistent source snapshot, and streams each table using PostgreSQL binary COPY with a target-side commit ledger.
6. Review per-table committed rows and transferred bytes.

For local testing, use two separate databases/instances and a dedicated least-privilege role. Do not use a production database. The pipeline does not currently copy foreign keys, secondary indexes, views, triggers, routines, grants or sequences. It may reject unsupported PostgreSQL DDL such as partitioned tables, generated columns or custom types.

## Tests

```powershell
cd backend
python -m unittest discover -s tests -v
```

## Architecture and roadmap

See [V2_DESIGN.md](V2_DESIGN.md), [implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md), [operations](docs/OPERATIONS.md), and [local development](docs/LOCAL_DEVELOPMENT.md).
