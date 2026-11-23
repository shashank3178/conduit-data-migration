# Local development: native PostgreSQL

Snowbridge uses your machine's native PostgreSQL server for its metadata database. pgAdmin is the administration UI; the PostgreSQL server service itself must be running.

## 1. Start and verify PostgreSQL

In Windows Services, ensure the PostgreSQL service for your installed version is running. In pgAdmin, connect to your local server and confirm its port (commonly `5432`). In Query Tool, run:

```sql
SELECT version(), current_setting('port');
```

## 2. Create the Snowbridge login role and database

In pgAdmin, connect to your local PostgreSQL server as an administrator (often `postgres`). Open **Tools → Query Tool**.

First execute this statement on its own, replacing the password with a strong password you choose:

```sql
CREATE ROLE snowbridge
    WITH LOGIN
    PASSWORD 'REPLACE_WITH_A_STRONG_PASSWORD';
```

Then execute this as a separate query:

```sql
CREATE DATABASE snowbridge_metadata
    OWNER snowbridge
    ENCODING 'UTF8';
```

**Important:** Run `CREATE DATABASE` separately; PostgreSQL does not permit it inside a transaction block. If the role or database already exists, do not re-run its CREATE statement. Check **Login/Group Roles** and **Databases** in pgAdmin first. Do not use the PostgreSQL superuser as the application's runtime identity.

## 3. Create your private backend/.env

From the repository root in PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
notepad backend/.env
```

Set the metadata DSN in `backend/.env`:

```dotenv
SNOWBRIDGE_METADATA_DATABASE_URL=postgresql://snowbridge:YOUR_PASSWORD@localhost:5432/snowbridge_metadata
```

Replace `YOUR_PASSWORD` with the role password you created. If it contains URI-reserved characters (for example `@`, `:`, `/`, `#`, or `%`), URL-encode the password component. Keep `backend/.env` private; the repository's root `.gitignore` excludes `.env` files. Commit only `.env.example`, which contains placeholders.

The backend loads `backend/.env` automatically through python-dotenv when `Settings.from_env()` is called. Existing process environment variables take precedence, so CI/production configuration is not overridden by the file.

## 4. Install dependencies and apply metadata migrations

```powershell
cd backend
python -m pip install -e .
python -m snowbridge.metadata.migrate --dsn "postgresql://snowbridge:YOUR_PASSWORD@localhost:5432/snowbridge_metadata"
```

The migration command takes an explicit DSN and does not currently read the DSN from Settings automatically; use the same value you put in `backend/.env`. (Application runtime configuration does load the file.)

Running the migration command again is safe: applied migration files are checksum-verified and skipped. Never edit an applied migration; add a new numbered SQL migration.

## 5. Verify

Refresh `snowbridge_metadata` in pgAdmin. Under **Schemas → public → Tables**, verify the metadata tables from `backend/sql/0001_metadata_schema.sql` and the `snowbridge_schema_migrations` ledger.

Run contract tests:

```powershell
python -m unittest discover -s tests -v
```

## 6. Integration-test database safety

The PostgreSQL adapter integration tests create and drop test schemas. Point `SNOWBRIDGE_TEST_DATABASE_URL` only at a disposable test database, never your metadata database or a source/target database containing data you need.

Create a separate `snowbridge_test` database in pgAdmin and assign ownership to the test role. Then:

```powershell
$env:SNOWBRIDGE_TEST_DATABASE_URL = "postgresql://snowbridge:YOUR_PASSWORD@localhost:5432/snowbridge_test"
python -m unittest discover -s tests -v
```

## Troubleshooting

- **Connection refused:** start the PostgreSQL Windows service and confirm host/port.
- **Password authentication failed:** reset the role password in pgAdmin and update `backend/.env`.
- **Database does not exist:** create `snowbridge_metadata` and check the DSN spelling.
- **Permission denied:** make `snowbridge` the owner of `snowbridge_metadata`; avoid granting superuser.
- **Port differs:** use the value returned by `current_setting('port')`.
