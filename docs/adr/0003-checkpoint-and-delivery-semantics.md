# ADR 0003: Durable checkpoints and replay-safe at-least-once execution

- Status: Accepted
- Date: 2026-11-23

## Context

The source and target generally do not participate in one distributed transaction. A process can fail after the target commits but before metadata records the checkpoint.

## Decision

Use stable task and batch identities, durable task leases, and at-least-once delivery with idempotent target application. Advance a checkpoint only after target commit confirmation. Store source position and target commit evidence where available. On ambiguous outcomes, replay safely or reconcile.

CDC ordering uses source log position plus transaction sequence, not wall-clock capture time. Transaction boundaries are preserved.

## Consequences

- Target apply implementations must document idempotency keys and conflict semantics.
- Retries are bounded and classified; poison events go to a durable DLQ with diagnosis.
- Exactly-once is not claimed across independent source/target systems.
- Metadata and target writes need explicit recovery tests for the commit/checkpoint gap.
