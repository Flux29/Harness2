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

## ISSUE-2 — Legacy-strata type errors excluded from pyright (owner: ADR 6.5)

**Status:** open · owner **ADR 6.5** · manifest: `disc-typecheck-gate-miscalibrated`.

`src/eval_optimizer/loop.py` (15 errs) and `graph.py` (2 errs) are excluded from
the eval-optimizer pyright scope (`[tool.pyright] exclude` in `pyproject.toml`).
These are the superseded generations ADR 6.5 will delete or relocate — type-
checking code slated for removal is wasted effort.

**Expiry (monotonic, like the dup-allowlist):** when ADR 6.5 lands, the two
`exclude` lines MUST be deleted — either the files are gone (delete → nothing to
exclude) or the ADR explicitly re-owns them (e.g. moved to `legacy/` and kept
out of the typed live path). No exclusion survives 6.5 without a living owner.

## ISSUE-3 — Non-legacy deferred type debt (owners: Phase 4.1 / 4.2)

**Status: CLOSED (Phase 4.1 + 4.2)** · manifest: `disc-typecheck-gate-miscalibrated`.

Genuine deferred type debt (NOT deletion candidates), excluded from pyright now
so the gate is green, each owned by the phase that already touches the file:

- ~~`src/eval_optimizer/memory_pg.py` (9 errs — psycopg SQL/optional typing)~~
  **RESOLVED in Phase 4.2:** queries recomposed with `psycopg.sql.Identifier`
  (on top of the KNOWN_AGENTS whitelist), `fetchone()` None-guards added,
  exclude dropped, pyright covers the file.
- ~~`src/eval_optimizer/check_connection.py` (3 errs — optional access)~~
  **RESOLVED in Phase 4.1:** types fixed (typed tools list, discriminated
  tool-call narrow), exclude dropped, pyright covers the file.

When each owner phase lands, remove that file's `exclude` line and let pyright
cover it.

## Pointer — other deferred findings

Every other deferred finding lives in `parity/findings-catalog.yml` +
`parity/manifest.yml` with its owning step (e.g. `disc-mcp-config-cwd-relative`
→ 4.7, `crit-fork-selection-metric` → 6.1). This file only adds the ones the plan
calls out for an explicit tracked issue.
