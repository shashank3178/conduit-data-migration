# Phase 3 implementation notes

## Included
- Authenticated discovery endpoints mounted under each project connection.
- Snapshot persistence in metadata PostgreSQL (one current snapshot per connection).
- Schema catalog (system schemas marked; their relations are not enumerated).
- Tables, views, materialized views, columns, PKs, FKs, unique/check constraints, indexes, comments, and planner row estimates.
- Refresh replaces catalog metadata transactionally; existing snapshot is retained if a refresh fails.
- Driver error messages are sanitized to avoid returning credentials/DSNs.
- SQLAlchemy inspector values are converted to JSON-safe metadata before persistence.

## Validation
Run from `backend/`:

```powershell
python -m pip install -e ".[dev]"
pytest -q
ruff check app tests
alembic upgrade head
```

Then use Swagger and the API flow in `DATABASE_DISCOVERY.md`.
