# Migration planning

A plan snapshots source/destination discovery metadata and defines selected source tables and destination column mappings. Planning does not move rows.

## Workflow
1. Complete discovery on both connections.
2. Create a plan under the project.
3. Select regular source tables and destination schema/table names.
4. Review/edit each table's mappings.
5. Validate.
6. Preview and apply destination DDL.
7. Continue to Migration execution.

## Mapping algorithm
In app/services/migration_plan_service.py:
- create_plan() pairs destination tables by exact schema+table name and stores candidate records.
- _suggest_column_mappings() matches exact column names for existing targets; unmatched columns remain excluded/unmapped. New targets get same source name/type suggestions.
- types_compatible() in app/services/migration_ddl.py checks normalized equality and conservative widening rules. It does not infer arbitrary casts or semantic/fuzzy matches.
- update_column_mappings() persists manual changes. Execution uses these saved mappings.

## API
- POST/GET /projects/{project_id}/migration-plans
- GET/PATCH /projects/{project_id}/migration-plans/{plan_id}
- GET /projects/{project_id}/migration-plans/{plan_id}/tables
- PUT /projects/{project_id}/migration-plans/{plan_id}/tables/selection
- POST /projects/{project_id}/migration-plans/{plan_id}/mappings/suggest
- PUT /projects/{project_id}/migration-plans/{plan_id}/tables/{table_id}/mappings
- POST /projects/{project_id}/migration-plans/{plan_id}/validate
- GET /projects/{project_id}/migration-plans/{plan_id}/ddl
- POST /projects/{project_id}/migration-plans/{plan_id}/ddl/apply

DDL builder quotes identifiers and allows only approved PostgreSQL types. It creates missing schemas/tables; advanced constraints, indexes, defaults, and identity/generated semantics require review.
