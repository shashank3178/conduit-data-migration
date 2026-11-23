# ADR 0005: Target-local idempotency and metadata checkpoint recovery

- Status: Accepted
- Date: 2026-11-23

## Context

The target database and Snowbridge metadata database cannot generally participate
in one distributed transaction. A worker can crash after target commit but before
the metadata checkpoint is written.

## Decision

Each target chunk transaction writes a durable row to
snowbridge_internal.chunk_commits in the same transaction as the data.
The row contains a stable chunk identity, immutable plan digest, commit token,
row count and byte count. A retry with the same identity and digest returns the
existing receipt without applying the data again. Reusing an identity with a
different digest is a hard conflict.

After target commit confirmation, the worker writes the metadata checkpoint.
If it crashes between those operations, replay reads the target ledger and
recreates the missing metadata checkpoint. Task acknowledgement follows the
checkpoint.

This is at-least-once execution with replay-safe target effects, not distributed
exactly-once delivery.

## Consequences

- Every target load path must execute inside the transaction passed to the
  idempotency wrapper; the callback must not commit independently.
- The digest must be derived from immutable run/snapshot/table/chunk planning
  data, not from a mutable retry attempt number.
- A completed target ledger row is retained for the life of the run's recovery
  window; cleanup must not precede metadata checkpoint durability.
- Reconciliation remains necessary to prove source/target content equivalence.
