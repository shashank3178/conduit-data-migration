# Phase 2: bounded concurrent migration writers

The keyset execution loop now pipelines source reads with independent destination writers.

## Runtime behavior

- `CONDUIT_MIGRATION_WRITERS` controls destination writer count (default 2, hard maximum 4).
- The producer fetches source batches in primary-key order while destination writer threads load earlier batches.
- Each writer owns a separate PostgreSQL destination connection and a separate SQLAlchemy metadata session.
- Each writer uses the existing COPY/staging/merge implementation and existing row-level error isolation.
- The in-flight queue is bounded to two batches per writer. When it fills, the producer waits for the oldest submitted batch before fetching more. This bounds queued row memory and applies backpressure.
- The coordinator commits batch metrics and the table's `last_key` checkpoint in original source-key order. A later batch can never advance the checkpoint past an earlier failed batch.
- Each `migration_run_tables` row remains an independent table partition with its own checkpoint. Batch metrics retain each committed batch's start/end key.

## Configure

Default (2 destination writers):

```env
CONDUIT_MIGRATION_WRITERS=2
```

Conservative / fallback:

```env
CONDUIT_MIGRATION_WRITERS=1
```

Higher concurrency (capped at 4):

```env
CONDUIT_MIGRATION_WRITERS=4
```

Restart both the API process and Celery worker after changing the environment.

## Recovery and transaction boundary

Destination data writes and metadata checkpoint commits are separate database transactions because they target different databases. A destination batch may commit just before the worker crashes and before its metadata checkpoint is committed. On restart, that batch can be replayed. This is safe for the supported writer strategies because INSERT-only uses `ON CONFLICT DO NOTHING` and UPSERT updates mapped values to the same source values. Checkpoint advancement itself remains ordered and is committed atomically with the batch metric in the metadata database.

The coordinator waits for futures in submission order even if later writers finish first. If an earlier batch fails, no later checkpoint is persisted. Already committed later destination batches may be replayed; the conflict behavior above makes that replay idempotent.

## Scope and limitations of this first cut

This is a bounded producer/consumer pipeline with concurrent destination COPY writers. Source extraction is overlapped with destination loading, but one source connection still fetches batches sequentially; multiple independent source readers / key-range partitioning are not implemented yet. The table is the durable checkpoint partition; this does not yet create independently resumable key ranges within one table.

Validation remains after table loading and is not parallelized. Start with 2 writers; increase to 4 only when source/destination connection limits and database load allow it. Compare Phase 1 stage timings and end-to-end throughput before/after.
