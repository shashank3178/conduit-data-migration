# PostgreSQL connections

## Configuration

Add the following setting to `.env` (never commit the real key):

```env
CONNECTION_ENCRYPTION_KEY=<Fernet key>
```

Generate a key once and keep it stable across restarts and deployments:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Back up this key in your secret manager. If it is lost or changed, previously stored connection passwords cannot be decrypted. Do not use a new key on each deployment.

## Metadata database setup

From the repository root:

```bash
docker compose up -d metadata-db
```

The Compose service initializes the PostgreSQL server and creates the `conduit_metadata` database and `conduit` role from its environment variables on the first volume initialization. Set `DATABASE_URL` in `backend/.env` to match.

Then apply the metadata schema:

```powershell
cd backend
python -m pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

Alembic creates/updates the tables. The database server/database must be reachable first; migrations do not provision a remote PostgreSQL server or database.

## API

All endpoints require an Auth0 access token with the configured API audience. Every operation is scoped to the authenticated user's project.

- `POST /api/v1/projects/{project_id}/connections` — register a source or destination.
- `GET /api/v1/projects/{project_id}/connections` — list project connections.
- `GET /api/v1/projects/{project_id}/connections/{connection_id}` — get connection metadata.
- `PATCH /api/v1/projects/{project_id}/connections/{connection_id}` — update metadata and/or replace password.
- `DELETE /api/v1/projects/{project_id}/connections/{connection_id}` — delete.
- `POST /api/v1/projects/{project_id}/connections/{connection_id}/test` — open a real PostgreSQL connection and run a small identity/version query.

Passwords are encrypted with Fernet before persistence and are never included in API responses. The encryption key is separate from the metadata database.
