# Snowbridge — Enterprise Database Migration Platform

Snowbridge is a clean-room V2 database migration platform. Development happens on `v2/rebuild`; this branch is deliberately independent of the V1 application on `main`.

> **Status:** Phase 2 discovery/planning adapters and canonical inventory are implemented on `v2/rebuild` for PostgreSQL, MySQL and Oracle. Live cross-engine qualification is still required. This repository does not yet claim production-ready migration execution, CDC, or reconciliation.

## Branch and product boundaries

- Product name: **Snowbridge**.
- `main` remains the historical V1 Conduit application.
- `v2/rebuild` is the Snowbridge V2 line. Do not merge V2 into `main` or open PRs targeting `main`.
- The GitHub repository slug remains `conduit-data-migration` for continuity; the product/application identity is Snowbridge.
- No V1 runtime code or migration implementation is reused by Snowbridge.

## Architecture

Snowbridge separates the management plane (projects, connections, plans, policy) from the data plane (snapshot extraction, CDC, bulk load, reconciliation). Database-specific behavior lives behind source and target adapter contracts. Durable task leases and checkpoints make work restartable; bounded streaming and backpressure keep memory independent of total table size.

See:
- [Architecture overview](docs/architecture/README.md)
- [Architecture decision records](docs/adr/)
- [Domain and adapter contracts](docs/contracts/README.md)
- [Metadata schema](backend/sql/0001_metadata_schema.sql)
- [Implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md)
- [Operations, recovery and security](docs/OPERATIONS.md)
- [Local development with native PostgreSQL](docs/LOCAL_DEVELOPMENT.md)
- [Benchmark and test strategy](docs/TEST_STRATEGY.md)

## First vertical slice

PostgreSQL-to-PostgreSQL snapshot only:
1. Secure connection references and capability preflight.
2. Schema discovery and conservative DDL planning.
3. A consistent source snapshot shared by bounded parallel readers.
4. Streaming extraction and PostgreSQL `COPY FROM STDIN` target loading.
5. Durable task/chunk checkpoints committed only after target commit.
6. Initial reconciliation and restart/failure-injection tests.

CDC and heterogeneous adapters follow only after this slice is correct and recoverable.

## Development status

The Python package in `backend/src/snowbridge` defines executable domain contracts and state-transition guards. It is intentionally not an end-to-end migration engine yet. SQL is the initial metadata schema proposal and must be applied through a versioned migration system before deployment.

## Local development

Use a native PostgreSQL installation on your machine (for example, PostgreSQL managed through pgAdmin). Docker Compose is not part of the local development workflow. Follow [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) to create the local role/database, configure the DSN, and apply metadata migrations.

The GitHub Actions CI job provisions its own disposable PostgreSQL service for automated integration checks; this does not require or use your local Docker setup.

## Local contract tests

Requires Python 3.11+.

```bash
cd backend
python -m unittest discover -s tests -v
```

## Non-goals

- No table-size-proportional in-memory buffering.
- No OFFSET-based large-table pagination.
- No silent lossy type conversion or skipped row errors.
- No claim of distributed exactly-once delivery across unrelated databases.
- No Kafka, Redis, Kubernetes, or workflow engine dependency until measured requirements justify the operational cost.
- No production readiness claim until integration, recovery, security, and scale gates pass.

## License and security

Do not commit credentials, connection strings containing secrets, customer data, or production dumps. Credentials are represented by opaque secret references; resolve them only at runtime through a secret-provider boundary.


## Phase 2 — Discovery and planning

The discovery layer provides a common schema inventory for PostgreSQL, MySQL and Oracle, capability preflight, conservative cross-engine type mapping, and catalog-based row/byte estimates. Install optional vendor drivers with:

```bash
cd backend
python -m pip install -e ".[discovery]"
```

Use the adapter APIs in `snowbridge.connection_manager` and `snowbridge.discovery`. Credentials are resolved from a `SecretReference`; they are not persisted in connection specifications. Catalog estimates are explicitly marked as estimates and must not be treated as exact snapshot counts. See `docs/IMPLEMENTATION_ROADMAP.md` for remaining live qualification.
