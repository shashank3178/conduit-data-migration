# Phase 4 — Migration planning

Phase 4 creates a persisted migration plan from completed Phase 3 discovery snapshots. It does not copy application rows.

## Workflow

1. Register and test source and destination PostgreSQL connections.
2. Run discovery for both connections.
3. Create a migration plan under a project. All discovered source relations are copied into the plan as candidates; only regular tables can be selected.
4. Select tables and optionally rename their destination schema/table.
5. Review suggested column mappings. Exact-name matches are suggested for existing destination tables; new destination tables start with same-name/same-type mappings.
6. Edit mappings and validate the plan.
7. Preview destination DDL, then explicitly apply it. DDL preparation creates missing schemas/tables only; it never truncates or drops existing objects and never transfers rows.

## API

All endpoints require an Auth0 bearer token and are under `/api/v1`.

- `POST /projects/{project_id}/migration-plans` — create a plan. Body: `name`, `description`, `source_connection_id`, `destination_connection_id`, `create_schemas`.
- `GET /projects/{project_id}/migration-plans` — list plans.
- `GET /projects/{project_id}/migration-plans/{plan_id}` — plan details.
- `PATCH /projects/{project_id}/migration-plans/{plan_id}` — update name, description, or schema-creation preference.
- `GET /projects/{project_id}/migration-plans/{plan_id}/tables` — list table candidates and mappings.
- `PUT /projects/{project_id}/migration-plans/{plan_id}/tables/selection` — bulk update selection and target names. Each item contains `table_id`, `selected`, `destination_schema`, `destination_table`.
- `POST /projects/{project_id}/migration-plans/{plan_id}/mappings/suggest` — regenerate automatic suggestions.
- `PUT /projects/{project_id}/migration-plans/{plan_id}/tables/{table_id}/mappings` — replace mappings for one table.
- `POST /projects/{project_id}/migration-plans/{plan_id}/validate` — validate and set plan status to `ready` when valid.
- `GET /projects/{project_id}/migration-plans/{plan_id}/ddl` — preview DDL statements and warnings.
- `POST /projects/{project_id}/migration-plans/{plan_id}/ddl/apply` — apply safe CREATE SCHEMA / CREATE TABLE statements to the destination.

## DDL safety

Identifiers are quoted. Destination types are restricted to a PostgreSQL type allow-list; arbitrary SQL type strings are rejected. DDL is transactional on PostgreSQL. Existing tables are not modified. Defaults/generated expressions, foreign keys, check constraints, indexes, and identity properties are not copied automatically in this prototype; the DDL preview returns warnings so they can be reviewed. This phase does not perform row transfer.

## Validation

Run from `backend/`:

```powershell
python -m pip install -e ".[dev]"
ruff check app tests
pytest -q
alembic upgrade head
alembic current
alembic heads
```

Expected Alembic head: `b7a4c2d9e610`.
