# PostgreSQL database discovery (Phase 3)

Discovery inspects a registered PostgreSQL connection and stores a metadata snapshot in the CONDUIT metadata database. It never copies row data or changes the remote database.

## Apply migration / start API

```powershell
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

## API (Auth0 bearer token required)

- `POST /api/v1/projects/{project_id}/connections/{connection_id}/discover` — refresh discovery.
- `GET /api/v1/projects/{project_id}/connections/{connection_id}/discovery` — latest snapshot/status.
- `GET /api/v1/projects/{project_id}/connections/{connection_id}/schemas` — schemas (system schemas marked).
- `GET /api/v1/projects/{project_id}/connections/{connection_id}/tables?schema=public` — table/view summaries.
- `GET /api/v1/projects/{project_id}/connections/{connection_id}/tables/{table_id}` — columns, PK, FKs, unique/check constraints, indexes, comment.

Use Swagger at `http://localhost:8000/docs`. First obtain the API token from the signed-in frontend's `/auth/access-token` endpoint and authorize Swagger with `Bearer <token>`.

## Metadata

A snapshot is unique per registered connection. Re-running discovery replaces that connection's schema/table snapshot atomically. It captures schemas, regular tables, views/materialized views, column attributes, PKs, FKs, unique/check constraints, indexes, table comments, and planner-statistics row estimates. System schemas are listed but their tables are skipped.

## Permissions / limitations

The remote PostgreSQL role needs CONNECT and sufficient catalog visibility; table metadata and statistics may be restricted. Row estimates are approximate, not exact counts. Discovery is synchronous and intended for prototype-sized schemas; large catalogs may require a background job in a later phase. Error responses deliberately avoid raw driver exception text and connection strings.
