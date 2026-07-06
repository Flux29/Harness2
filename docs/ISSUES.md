# Tracked issues (deferred decisions)

Lightweight issue log for known problems whose fix is deferred to a later phase
by `docs/HarnessRefactor.md`. The machine-canonical state is `parity/manifest.yml`;
this file is the human-readable "don't silently forget" list for items that need
an ADR before any code or doc change.

## ISSUE-1 — Checkpoint persistence claimed but per-request ephemeral

**Status: CLOSED (ADR-0019, 2026-07-06)** · manifest: `crit-checkpoint-persistence`.

Resolved as **Option A, split along the layer boundary**: `make_deps` now wires
a durable per-thread `FileCheckpointStore` under `state/checkpoints/<slug>/`
(the 5.1 server-only tree), so checkpoints and fork anchors survive across
requests and restarts — the storage prerequisite of the planned
deepresearch→CopilotKit port. The rewind endpoints/UI are ISSUE-4's checklist.
ADR-0015's row is annotated in place.

## ISSUE-4 — deepresearch→CopilotKit checkpoint surfacing (successor to ISSUE-1)

**Status:** open · owner: the deepresearch→CopilotKit integration ·
ADR-0019's deferred half.

The storage layer exists (ADR-0019); the user-facing surface does not yet.
The integration's checkpoint checklist, mirroring the vendor reference app
(`apps/deepresearch`):

- AG-UI-surface equivalents of `GET /checkpoints`,
  `POST /checkpoints/{id}/rewind`, `POST /checkpoints/{id}/fork`
  (`fork_from_checkpoint`).
- App-level `RewindRequested` handling in the web layer (restore + persist
  history, notify the client). **Until this lands, an agent-invoked
  `rewind_to` on the web path surfaces as a run error** — known limitation;
  any such error in telemetry is the tripwire to prioritize this item.
- CopilotKit UI affordances: checkpoint timeline + per-message Rewind/Fork
  controls (the deepresearch pattern, `static/app.js`).

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
