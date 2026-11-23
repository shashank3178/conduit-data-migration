-- Snowbridge initial metadata schema proposal (PostgreSQL 15+).
-- Apply through a versioned migration runner; do not execute ad hoc in production.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE secret_references (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    provider text NOT NULL,
    secret_id text NOT NULL,
    secret_version text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, provider, secret_id, secret_version)
);

CREATE TABLE connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    name text NOT NULL,
    engine text NOT NULL,
    endpoint jsonb NOT NULL,
    secret_reference_id uuid NOT NULL REFERENCES secret_references(id),
    discovered_version text,
    last_tested_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);

CREATE TABLE schema_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id uuid NOT NULL REFERENCES connections(id),
    captured_at timestamptz NOT NULL DEFAULT now(),
    database_name text NOT NULL,
    engine_version text,
    inventory jsonb NOT NULL,
    inventory_checksum text
);

CREATE TABLE migration_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id),
    source_connection_id uuid NOT NULL REFERENCES connections(id),
    target_connection_id uuid NOT NULL REFERENCES connections(id),
    source_snapshot_id uuid REFERENCES schema_snapshots(id),
    target_snapshot_id uuid REFERENCES schema_snapshots(id),
    status text NOT NULL DEFAULT 'draft',
    configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_connection_id <> target_connection_id)
);

CREATE TABLE migration_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id uuid NOT NULL REFERENCES migration_plans(id),
    state text NOT NULL DEFAULT 'draft',
    source_snapshot_token text,
    cdc_start_position jsonb,
    cdc_current_position jsonb,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE migration_tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES migration_runs(id),
    task_type text NOT NULL,
    object_schema text,
    object_name text,
    state text NOT NULL DEFAULT 'pending',
    priority integer NOT NULL DEFAULT 100,
    attempt integer NOT NULL DEFAULT 0,
    lease_owner text,
    lease_expires_at timestamptz,
    last_error_category text,
    last_error_detail text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX migration_tasks_claim_idx
    ON migration_tasks (state, priority, created_at)
    WHERE state IN ('pending', 'retry');

CREATE TABLE migration_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL REFERENCES migration_tasks(id),
    stable_key text NOT NULL,
    snapshot_id uuid,
    range_spec jsonb NOT NULL,
    max_rows bigint NOT NULL CHECK (max_rows > 0),
    max_bytes bigint NOT NULL CHECK (max_bytes > 0),
    state text NOT NULL DEFAULT 'pending',
    attempt integer NOT NULL DEFAULT 0,
    rows_committed bigint NOT NULL DEFAULT 0,
    bytes_committed bigint NOT NULL DEFAULT 0,
    target_commit_token text,
    completed_at timestamptz,
    UNIQUE (task_id, stable_key)
);

CREATE TABLE migration_checkpoints (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES migration_runs(id),
    task_id uuid NOT NULL REFERENCES migration_tasks(id),
    chunk_id uuid NOT NULL REFERENCES migration_chunks(id),
    source_position jsonb,
    target_commit_token text NOT NULL,
    committed_rows bigint NOT NULL,
    committed_bytes bigint NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (chunk_id)
);

CREATE TABLE reconciliation_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES migration_runs(id),
    tier smallint NOT NULL CHECK (tier BETWEEN 0 AND 4),
    source_watermark jsonb,
    target_watermark jsonb,
    state text NOT NULL,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE TABLE reconciliation_results (
    id bigserial PRIMARY KEY,
    reconciliation_run_id uuid NOT NULL REFERENCES reconciliation_runs(id),
    object_schema text NOT NULL,
    object_name text NOT NULL,
    bucket_key text,
    source_count bigint,
    target_count bigint,
    source_digest text,
    target_digest text,
    mismatch_category text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE dead_letter_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES migration_runs(id),
    task_id uuid REFERENCES migration_tasks(id),
    source_schema text,
    source_table text,
    primary_key jsonb,
    source_position jsonb,
    payload_reference text,
    error_category text NOT NULL,
    sanitized_error text NOT NULL,
    retry_count integer NOT NULL DEFAULT 0,
    resolution text,
    operator_action text,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);
CREATE INDEX dead_letter_open_idx ON dead_letter_records (run_id, created_at)
    WHERE resolved_at IS NULL;

CREATE TABLE audit_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    actor_id text,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_tenant_time_idx ON audit_events (tenant_id, occurred_at DESC);

-- High-frequency metrics belong in OpenTelemetry/metrics storage, not hot rows here.
