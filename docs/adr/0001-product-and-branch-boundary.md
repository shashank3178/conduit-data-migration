# ADR 0001: Snowbridge product identity and V2 branch boundary

- Status: Accepted
- Date: 2026-11-23

## Context

V1 has operational and correctness limitations and must remain available as a historical application. V2 is a clean rebuild, not a refactor of the V1 execution pipeline.

## Decision

The V2 product/application name is **Snowbridge**. Development remains on `v2/rebuild`; `main` remains V1. V2 must not be merged into `main`. The GitHub repository slug is retained for continuity and is not itself the product name.

## Consequences

- All new package names, docs, UI labels, telemetry service names and configuration prefixes use `snowbridge`.
- No V1 imports, database schema assumptions, or deployment artifacts are dependencies of V2.
- Branch protection should prohibit accidental PRs/merges from V2 to main; configure this in GitHub settings outside code.
- Historical V1 assets remain reachable on `main`.
