# ADR 0004: Bounded streaming snapshot execution

- Status: Accepted
- Date: 2026-11-23

## Decision

Snapshot extraction and target writes are streaming, byte-bounded and concurrency-limited. Chunk planning prefers indexed primary/unique key ranges; no OFFSET pagination for large tables. Chunk limits include both rows and estimated/observed bytes. LOBs have a separate streaming path.

Concurrency is adaptive but bounded per endpoint. Backpressure considers source and target CPU/I/O, connection pool saturation, memory, lock waits, CDC lag and source log retention.

## Initial tuning hypotheses

Use byte budgets as the hard safety bound. Candidate starting ranges from the project requirements: snapshot chunks around 25–250 MB for narrow/medium rows and 32–128 MB ceiling for wide/LOB paths; write batches around 16–64 MB. Start with a small reader pool (for example 4) and increase only from measured throughput and resource headroom. These are not universal defaults and must be validated per driver, schema and database.

## Consequences

- A single oversized row must not violate the process memory budget; stream LOBs or isolate them.
- Adaptive control needs hysteresis to avoid concurrency oscillation.
- Benchmarks record throughput and correctness together.
