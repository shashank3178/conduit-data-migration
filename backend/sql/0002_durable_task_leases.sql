-- Durable worker leases with fencing tokens and bounded retry scheduling.
-- Existing applied migrations are immutable; all evolution is additive here.

ALTER TABLE migration_tasks
    ADD COLUMN IF NOT EXISTS lease_token uuid,
    ADD COLUMN IF NOT EXISTS leased_at timestamptz,
    ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz,
    ADD COLUMN IF NOT EXISTS available_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS completed_at timestamptz;

ALTER TABLE migration_tasks
    ADD CONSTRAINT migration_tasks_max_attempts_positive
    CHECK (max_attempts > 0);

CREATE INDEX IF NOT EXISTS migration_tasks_claimable_idx
    ON migration_tasks (priority, available_at, created_at)
    WHERE state IN ('pending', 'retry', 'running');

CREATE INDEX IF NOT EXISTS migration_tasks_lease_expiry_idx
    ON migration_tasks (lease_expires_at)
    WHERE state = 'running';

COMMENT ON COLUMN migration_tasks.lease_token IS
    'Fencing token; every heartbeat/completion/failure must match the current token.';
COMMENT ON COLUMN migration_tasks.available_at IS
    'Earliest time a pending or retry task may be claimed.';
COMMENT ON COLUMN migration_tasks.max_attempts IS
    'Maximum total claims before the task becomes terminally failed.';
