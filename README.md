# Conduit Data Migration — V2

V2 is a clean rebuild of Conduit. It is intentionally developed on the `v2/rebuild` branch and is not intended to be merged into `main`.

## Branch isolation

- `main` remains the V1 application and is the source of truth for V1.
- `v2/rebuild` is the independent V2 development line.
- V2 changes must stay on V2 branches. Do not open pull requests targeting `main`.
- V1 source, migration engines, and validation code are not carried forward into the V2 working tree.

## Current state

The V2 branch has been reset to a minimal design baseline. No V1 migration engine or V1 validation implementation is present here yet. V2 implementation starts from a new architecture; see [V2_DESIGN.md](V2_DESIGN.md).

## Development

Clone and switch explicitly to V2:

```bash
git clone https://github.com/shashank3178/conduit-data-migration.git
cd conduit-data-migration
git switch v2/rebuild
```
