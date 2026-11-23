# Operations, security and recovery

## Credentials and network

Persist opaque secret references, not plaintext credentials. Resolve secrets at worker runtime through a provider interface (cloud secret manager, Vault, or local development provider). Enforce TLS where supported, least-privilege source/target accounts, rotation, tenant isolation and audit. Redact DSNs, tokens, bind values and row payloads from logs. Clean temporary files on success, failure and cancellation.

## Backpressure and safety stops

Pause scheduling new chunks when source/target CPU or I/O is saturated, memory approaches configured limits, connection pools are exhausted, lock waits rise, CDC lag breaches policy, source log retention is at risk, or DLQ growth indicates systemic failure. Resume with hysteresis and operator-visible reasons. Never solve pressure by unbounded queues.

## Recovery matrix

| Failure | Required behavior |
|---|---|
| Worker dies mid-read | Lease expires; chunk is retried from the same snapshot if still valid |
| Snapshot expires | Stop affected tasks and establish a new consistent snapshot according to plan; never mix snapshots silently |
| Target disconnect before commit | Roll back/retry batch |
| Target commit outcome ambiguous | Replay idempotently or reconcile before advancing |
| Metadata write fails after target commit | Retry checkpoint after confirming/replaying safely |
| API/backend restart | Restore run/task state from metadata |
| Source disconnect | Reconnect from safe snapshot/log position or stop if boundary expired |
| PostgreSQL slot/WAL pressure | Backpressure and alert before retention exhaustion |
| MySQL binlog gap / Oracle redo gap | Mark CDC continuity unrecoverable; require re-snapshot or operator recovery |
| Target disk full | Pause, alert and preserve checkpoint |
| Schema drift | Apply configured stop/warn/transform policy |
| Reconciliation mismatch | Isolate table/bucket; do not mark cutover-ready |

## Migration state machine

`DRAFT → PREFLIGHT → SNAPSHOT → CDC_CATCHUP → RECONCILIATION → CUTOVER_READY → CUTOVER → COMPLETED`

Controlled side states: `PAUSED`, `FAILED`, `CANCELLED`, `ROLLING_BACK`. Transitions are guarded and audited. Terminal states cannot silently return to active execution.

## Cutover

Freeze source writes, capture a final source log boundary, drain target apply through that boundary, reconcile at the same logical watermark, evaluate DLQ and schema gates, then switch traffic. Rollback after target writes requires reverse CDC or an explicit restore/replay plan; do not simply point traffic back at the old source.

## Diagnostics

Errors carry stable category, phase, source/target object, task/chunk ID, source position, retryability, attempt and sanitized driver detail. DLQ entries preserve a safe payload reference, PK, source position, error category, retry count, resolution and operator action. Never silently discard row-level failures.
