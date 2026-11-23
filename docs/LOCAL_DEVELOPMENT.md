# Local development: native PostgreSQL

Snowbridge's metadata database should run on your machine's PostgreSQL installation, not in a Docker container. pgAdmin is only the administration UI; the PostgreSQL server service must be running locally.

## 1. Start and verify PostgreSQL

In Windows Services, ensure the PostgreSQL service for your installed version is running. In pgAdmin, connect to your local server and confirm its port (commonly `5432`). You can verify from a terminal:

```powershell
pg_isready -h localhost -p 5432
```

If `pg_isready` is not on PATH, use pgAdmin's Query Tool to run:

```sql
SELECT version(), current_setting('port');
```

## 2. Create a dedicated role and metadata database

In pgAdmin, connect to your local server as an administrator (often `postgres`), open **Tools → Query Tool**, and run the following. Replace the password with a strong local development password before executing:

```sql
CREATE ROLE snowbridge LOGIN PASSWORD 'REPLACE_WITH_A_STRONG_PASSWORD';
CREATE DATABASE snowbridge_metadata OWNER snowbridge;
```

If you already created either object, do not run the corresponding CREATE statement again. Check **Login/Group Roles** and **Databases** in pgAdmin first. The dedicated role should own the metadata database; do not use the PostgreSQL superuser as the application's runtime identity.

## 3. Configure the backend connection

From PowerShell, in the same terminal used to run Snowbridge:

```powershell
$env:SNOWBRIDGE_METADATA_DATABASE_URL = "postgresql://snowbridge:YOUR_PASSWORD@localhost:5432/snowbridge_metadata"
```

Replace `YOUR_PASSWORD`. If the password contains URI-reserved characters (such as `@`, `:`, `/`, `#`, or `%`), URL-encode the password component. Do not commit the DSN or put real credentials in `.env.example`.

Alternatively, copy `backend/.env.example` to a private local configuration file and load its values using your preferred environment-variable loader. The current package reads process environment variables; it does not automatically parse `.env` files.

## 4. Install and apply metadata migrations

```powershell
cd backend
python -m pip install -e .
python -m snowbridge.metadata.migrate --dsn $env:SNOWBRIDGE_METADATA_DATABASE_URL
```

The migration runner creates/updates the Snowbridge migration ledger and applies numbered SQL files in `backend/sql`. Running it again is safe: already-applied files are checksum-verified and skipped. Never edit a migration after it has been applied; add a new numbered migration instead.

## 5. Verify in pgAdmin

Refresh the `snowbridge_metadata` database in pgAdmin. Under **Schemas → public → Tables**, verify the metadata tables from `backend/sql/0001_metadata_schema.sql` and the `snowbridge_schema_migrations` ledger exist.

Then run contract tests:

```powershell
python -m unittest discover -s tests -v
```

## 6. Integration test database safety

The PostgreSQL adapter integration tests use `SNOWBRIDGE_TEST_DATABASE_URL` and create/drop test schemas. Point that variable only at a disposable local test database, never your metadata database or a source/target database containing data you need.

```powershell
$env:SNOWBRIDGE_TEST_DATABASE_URL = "postgresql://snowbridge:YOUR_PASSWORD@localhost:5432/snowbridge_test"
python -m unittest discover -s tests -v
```

Create `snowbridge_test` separately in pgAdmin and assign ownership to the test role before running those tests. The metadata database and integration-test database should be separate.

## Troubleshooting

- **Connection refused:** start the PostgreSQL Windows service and confirm host/port.
- **Password authentication failed:** reset the role password in pgAdmin and update the DSN in the current PowerShell session.
- **Database does not exist:** create `snowbridge_metadata` and ensure the DSN uses the exact name.
- **Permission denied:** make `snowbridge` the owner of `snowbridge_metadata`; avoid granting superuser.
- **Port differs:** use the port shown by `SHOW port;` in the DSN.
