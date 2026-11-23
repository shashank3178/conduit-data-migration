# ADR 0002: Separate source/target adapters and explicit capabilities

- Status: Accepted
- Date: 2026-11-23

## Decision

Source and target roles are independent contracts. A source adapter owns discovery, snapshot establishment, snapshot reads, and optional CDC capture. A target adapter owns schema application, bulk loading, change application, sequence synchronization and target-side reconciliation primitives.

Capabilities are negotiated per endpoint, database version, permissions and configuration. A successful TCP/database connection does not imply that CDC or a native bulk-load mode is available.

## Consequences

- Core orchestration depends on protocols and canonical models, never vendor drivers.
- Each capability reports availability, prerequisites, permission checks and a human-readable reason.
- Adapters must expose consistency and transaction semantics explicitly.
- Unsupported or lossy operations fail preflight or require an explicit transformation decision; no silent fallback.
