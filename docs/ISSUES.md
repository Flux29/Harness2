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

**Status: CLOSED (ADR-0021, 2026-07-06)** · manifest: `disc-typecheck-gate-miscalibrated`.

The two file excludes (`loop.py`, `graph.py`) are replaced by a single
`src/eval_optimizer/legacy` exclude: ADR-0021 relocated the whole Gen-1 stratum
to the committed, import-quarantined `legacy/` package (deferred, LLM nodes
stubbed), kept out of the typed live path — exactly the "moved to `legacy/` and
kept out of the typed live path" resolution this issue anticipated. The exclude
is owned by ADR-0021 and drops when the deferred integration resumes.

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

## ISSUE-5 — Fork `test_command` inherits the full parent environment

**Status:** open · owner: fork hardening · surfaced by ADR-0018, recorded by
ADR-0020 · manifest: `crit-fork-exec-gate` (adjacent).

The vendor test runner materializes a branch and runs its `test_command` with
`env = {**os.environ, "UV_NO_SYNC": "1"}` (its own documented SECURITY caveat,
`coordinator._run_tests_for_branch`): a branch's tests execute with whatever
secrets the parent process holds (OpenRouter/GitHub/Logfire tokens). This is a
known property, not a live hole, because forking is default-off (5.2,
`FORKING=0`) and the eval-optimizer path additionally requires
`EVALOPT_ALLOW_HOST_EXEC=1`. Hardening — scrubbing the child env for
`test_command` to a minimal allowlist (`PATH`/`HOME`/`SYSTEMROOT`/…) — is a
first-party wrapper concern (the vendor stays pristine) and is deferred until
forking is enabled in a deployment that matters. ADR-0020 §5.

## ISSUE-6 — Post-refactor floor raise: `>=3.13` workspace-wide

**Status:** open · owner: post-exit-gate-6 · recorded by ADR-0022's
acceptance note.

ADR-0022 set the transitional floor at 3.12 (the verified interpreter) to
keep the refactor's verification base stable. The acceptance ruling: once
exit gate 6 passes, raise `requires-python` to `>=3.13` in all three
first-party projects plus the root `.python-version`, rebuild the venvs,
re-verify against the v2 baselines gate 6 produces, and promote
`catalogs/models.yml` `target_floor_python` → `compatibility_python`. The
coherence tests (`evals/agentic-smoke/tests/test_workspace_coherence.py`)
enforce whichever floor is current, so the raise is one commit plus a
verification run. Standing constraint from the same note: coherence work
never narrows the vendor feature surface (ADR-0015's enablement goal
outlives the refactor).

## ISSUE-7 — Vendor: `BranchOverlay.grep_raw()` signature mismatch in fork branches

**Status:** open · owner: vendor patch decision · surfaced by the gate-6 live
session (first live fork run).

A branch agent calling its `grep` tool with pattern + path + options crashed
the branch: `TypeError: BranchOverlay.grep_raw() takes from 2 to 3 positional
arguments but 5 were given` (vendor `features/forking` overlay shim's `grep_raw`
signature lags the tool schema it fronts). The coordinator absorbed it
("result unreadable; falling back to partial_history") and the branch was
scored from partial history — fail-contained, not fail-clean. Vendor tree is
READ-ONLY (standing rule 1): the fix is a patch file + `VENDOR.txt` entry, or
an upstream report at the next re-vendor. Not gate-blocking: branches that
avoid grep are unaffected, and the selection path stays deterministic.

## Note — server-only `state/` retention

The `state/` tree (history since 5.1, checkpoints since ADR-0019) is the single
server-side PII surface. It has no auto-expiry today; checkpoints self-bound via
the vendor's `max_checkpoints=20` prune, but history and old thread dirs grow
unbounded. Recorded by ADR-0020 §6 as a known property for a future retention
decision (not changed there). No issue number — a property to weigh, not a bug.

## Pointer — other deferred findings

Every other deferred finding lives in `parity/findings-catalog.yml` +
`parity/manifest.yml` with its owning step (e.g. `disc-mcp-config-cwd-relative`
→ 4.7, `crit-fork-selection-metric` → 6.1). This file only adds the ones the plan
calls out for an explicit tracked issue.
