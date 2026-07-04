# Tracked issues (deferred decisions)

Lightweight issue log for known problems whose fix is deferred to a later phase
by `docs/HarnessRefactor.md`. The machine-canonical state is `parity/manifest.yml`;
this file is the human-readable "don't silently forget" list for items that need
an ADR before any code or doc change.

## ISSUE-1 — Checkpoint persistence claimed but per-request ephemeral (HOLD)

**Status:** open · deferred to Phase 6.3 (ADR required) · manifest:
`crit-checkpoint-persistence`.

ADR-0015 and the checkpoint docs claim durable, cross-request rewind, but the
web layer wires `InMemoryCheckpointStore()` per request (`deps.py`), so
checkpoints do not survive across requests. **Do not edit ADR-0015's checkpoint
claims yet** (plan step 2.6 explicitly holds): whether cross-request rewind is a
real requirement is the 6.3 decision —

- **Option A:** it is → implement a durable per-thread store (file-backed next to
  history in the 5.1 server-only tree) and keep the claim.
- **Option B:** it isn't → downgrade the documented claim to per-run checkpoints
  and keep `InMemoryCheckpointStore`.

The parity impact differs (A adds files to Matrix D; B changes only prose), so
the ADR lands before any code. Recorded here so the known-false claim is not lost
between now and Phase 6.

## Pointer — other deferred findings

Every other deferred finding lives in `parity/findings-catalog.yml` +
`parity/manifest.yml` with its owning step (e.g. `disc-mcp-config-cwd-relative`
→ 4.7, `crit-fork-selection-metric` → 6.1). This file only adds the ones the plan
calls out for an explicit tracked issue.
