# Migration execution engine redesign

## Engine contracts

All engines must preserve the same run lifecycle and reporting contract:

- A destination batch is acknowledged only after its destination transaction commits.
- The metadata checkpoint, batch metric, and run event are committed after the destination commit.
- A crash between destination commit and metadata commit is replay-safe: the prior checkpoint is replayed and INSERT/UPSERT conflict semantics make the retry idempotent.
- Validation is independent of the writer and compares source/destination rows by mapped primary key.
- Cancellation is cooperative between batches or native subprocess stages; workers must terminate child processes before marking a run cancelled.

## Phase 1: transactional COPY writer

`postgres_copy_engine.copy_stage_and_merge` creates a transaction-local staging table using the destination table's column types, streams a bounded in-memory batch through Psycopg COPY, and merges into the target with INSERT_ONLY or UPSERT semantics. The staging table and merge share one transaction. Row-level SQLSTATE failures are handled by the existing recursive batch isolation wrapper.

Rollout is opt-in on a worker with:

```powershell
$env:CONDUIT_WRITE_ENGINE = "copy"
```

Unset or set to `values` to retain the legacy VALUES writer. This switch is intentionally worker-scoped until integration tests and representative benchmarks establish safe defaults.

The new bounded extraction primitive uses independent source connections and disjoint integer-primary-key ranges. It limits memory to approximately `workers × batch_size` rows. It is currently a library primitive, not yet the default run scheduler; it requires a thread-safe batch consumer. UUID, composite, and non-integer keys continue through the sequential keyset path.

## Phase 2: native PostgreSQL engine

`postgres_native_engine.run_native_migration` runs directory-format `pg_dump` followed by parallel `pg_restore`. It:
- checks that pg_dump/pg_restore are installed;
- checks source/destination server major-version compatibility;
- bounds dump and restore job counts;
- keeps passwords in child-process environment variables, never command arguments;
- monitors elapsed time, supports cooperative cancellation, terminates process groups, and reports stderr on failure;
- removes temporary dump artifacts after completion.

This engine is for compatible database/schema cloning only. It does not apply column mappings, row transformations, application UPSERT policies, or per-row quarantine. Filtered dumps do not automatically include every dependency. A planner-level compatibility/dependency check and explicit destination-empty policy are required before wiring this service into the run queue. It must never be selected automatically for a transformed/table-mapped plan.

## Required integration gates before enabling either engine by default

1. Add persisted engine selection and validated API/UI choices.
2. Add a planner compatibility report for native dump/restore (schemas, extensions, ownership, privileges, sequences, foreign keys, views, functions, triggers, large objects, RLS, generated/identity columns).
3. Add run-level native process state, cancellation, heartbeat, and recovery policy. A partially restored native run must restart from a fresh destination or a verified restore strategy; it cannot be treated as a row-key checkpoint.
4. Add destination commit + metadata checkpoint fault-injection tests.
5. Run live PostgreSQL integration tests for JSON/JSONB, identity/generated columns, constraints, triggers, FK ordering, UPSERT, COPY errors, cancellation, and resume.
6. Benchmark VALUES versus COPY with identical data and destination state at 1 GiB, 10 GiB, and larger datasets. Report end-to-end throughput, memory, CPU, source fetch, destination merge, commit, and validation independently.

The 500 MB/s figure is a performance target, not a guarantee. Network bandwidth, RTT, source query plans, destination WAL/fsync, indexes, constraints, CPU, and provider limits are hard ceilings.
