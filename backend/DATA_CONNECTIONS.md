# Data connections

Connection records are owner/project-scoped and have source or destination role. PostgreSQL passwords are Fernet-encrypted before persistence in metadata PostgreSQL.

## Encryption key
Generate once and set CONNECTION_ENCRYPTION_KEY in backend/.env:
~~~powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
~~~
Keep it backed up in a secret manager. Losing/changing it prevents decrypting saved passwords.

## Metadata DB
From repository root: docker compose up -d metadata-db. Use DATABASE_URL=postgresql+psycopg://conduit:conduit@localhost:5433/conduit_metadata, then from backend run alembic upgrade head.

## API
Auth0 bearer token and project ownership are required:
- POST /api/v1/projects/{project_id}/connections — register
- GET /api/v1/projects/{project_id}/connections — list
- GET /api/v1/projects/{project_id}/connections/{connection_id} — details (no password)
- PATCH /api/v1/projects/{project_id}/connections/{connection_id} — update
- DELETE /api/v1/projects/{project_id}/connections/{connection_id} — remove
- POST /api/v1/projects/{project_id}/connections/{connection_id}/test — connect/test

Implementation: app/services/connection_service.py (encrypt_password, decrypt_password, test_connection) and app/api/routes/connections.py. Use least-privilege source credentials and SSL for remote databases.
