# Data discovery

Discovery reads PostgreSQL catalog metadata and stores a snapshot in CONDUIT metadata DB. It never transfers application rows or changes source data.

## Workflow
1. Register/test source and destination connections.
2. Run discovery on both.
3. Review schemas, relation types, columns, keys, constraints, indexes, comments, estimated rows.
4. Create a migration plan from completed snapshots.

## API
- POST /api/v1/projects/{project_id}/connections/{connection_id}/discover — refresh
- GET /api/v1/projects/{project_id}/connections/{connection_id}/discovery — status/snapshot
- GET /api/v1/projects/{project_id}/connections/{connection_id}/schemas — schemas
- GET /api/v1/projects/{project_id}/connections/{connection_id}/tables?schema=public — relations
- GET /api/v1/projects/{project_id}/connections/{connection_id}/tables/{table_id} — details

Implementation: app/services/discovery_service.py uses SQLAlchemy Inspector and PostgreSQL catalog queries. Metadata is normalized to JSON before persistence. Refresh is transactional; failed refresh retains the previous snapshot. System schemas are marked/skipped. Row estimates are planner estimates, not exact counts.

Discovery is synchronous in this build; very large catalogs may need background execution.
