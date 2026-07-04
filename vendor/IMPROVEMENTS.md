# Vendored pydantic-deepagents — Improvement Suggestions

Written 2026-07-01, against vendor @ `f2224c5` (0.3.34) with the one
`branch_outcomes()` patch. Companion to `RUNBOOK.md`. Ordered by value/effort.

> **Status 2026-07-01 (all 8 enacted):** #1 `patches/0001-branch-outcomes.patch`
> (round-trip verified) · #2 `.git` parked in `Obsolete/vendor-pydantic-deepagents/`
> + `VENDOR.txt` provenance · #3 in-tree `.venv` parked likewise; consumers own their
> venvs · #4 RUNBOOK retargeted to `[web,mcp,yaml]`, TUI = legacy · #5 `verify_core.py`
> extended (AG-UI import, MCP registry, parse fixture) · #6 `revendor_check.py` added ·
> #7 runtime-dir excludes noted in VENDOR.txt/RUNBOOK · #8 upstream-watch step added to
> the re-vendor procedure. Upstreaming the patch (PR) remains open.
> Nothing was deleted: parked files live in `Obsolete/` (git-ignored).

## 1. Formalize the patch as a diff file
The single local edit lives only as prose in the RUNBOOK. Create
`vendor/patches/0001-branch-outcomes.patch` (unified diff of
`pydantic_deep/features/forking/coordinator.py`, currently line ~1147). Re-vendoring
becomes mechanical: clone → `git apply ../patches/*.patch` → copy. Also the honest
long-term move stands: PR it upstream so the diff drops to zero.

## 2. Drop the dead `.git/` from the vendored tree
`vendor/pydantic-deepagents/.git/` exists but git can't operate inside AgenticWork
(RUNBOOK: "operation not permitted"). A non-functional `.git` is worse than none —
tools mis-detect a repo root and it silently pins stale metadata. Delete it and
record provenance in a tiny `vendor/pydantic-deepagents/VENDOR.txt`:
upstream URL, commit SHA, date, applied patches.

## 3. Move the venv out of the vendored tree
`vendor/pydantic-deepagents/.venv/` mixes ~100MB of build artifacts into what should
be pristine-source-plus-patch. Each consumer should own its venv
(`projects/agent-web/.venv`, `projects/eval-optimizer/.venv`) and install the vendor
editable: `uv pip install -e ../../vendor/pydantic-deepagents[web,mcp,yaml]`.
Re-vendoring then never risks clobbering an environment, and "what changed in
vendor/" stays reviewable.

## 4. Retarget install extras for the pivot (ADR-0012)
RUNBOOK's primary path installs `.[cli]` (Textual TUI). Post-pivot the web service
wants `.[web,mcp,yaml]` (+`sandbox` for Docker execute, +`browser` if enabled) plus
`pydantic-ai-slim[ag-ui]` on top — note `ag-ui` is **not** among the vendor's extras,
it comes from pydantic-ai itself. Suggested RUNBOOK edit: keep the TUI section as
legacy, promote the web install to the primary path. Skip `.[all]` — it drags in
TUI, ACP, and liteparse (which needs Node in the *Python* service; the only Node we
want is the CopilotKit frontend).

## 5. Extend `verify_core.py` for the new surface
Today it proves imports + forking + patch + OpenRouter. Add three cheap, no-network
checks: `from pydantic_ai.ui.ag_ui import AGUIAdapter` (AG-UI installed),
`from pydantic_deep.mcp import MCPRegistry, parse_mcp_servers, builtin_mcp_servers`
(mcp extra live), and `parse_mcp_servers()` on a two-entry fixture (stdio + http)
returns 2 configs. That makes verify_core the single gate for both consumers after
any re-vendor.

## 6. Add a re-vendor smoke script
The RUNBOOK's manual copy procedure has a known failure mode ("large writes can
truncate silently"). A ~20-line `vendor/revendor_check.py` that compares file count +
sha256 of `pydantic_deep/**/*.py` between clone and vendor copy turns "always verify
after copying" from advice into a command.

## 7. Trim `apps/` weight consciously (optional)
`apps/cli` (TUI) and `apps/harbor` are now officially out of scope (ADR-0015), and
`apps/deepresearch` carries `workspace/`/`workspaces/` runtime dirs. Keeping the
source is fine (it's the point of vendoring); just add those runtime dirs to any
backup/sync excludes, and don't install their extras. If disk/pull time ever
matters, `apps/` can be pruned at re-vendor with a note in VENDOR.txt.

## 8. Watch upstream for an AG-UI-aware release
Upstream ships `examples/full_app` with a bespoke WebSocket protocol. If a future
release adopts the `pydantic_ai.ui` adapters (or grows an `ag-ui` extra), our
`projects/agent-web` endpoint likely shrinks further — check CHANGELOG.md on each
re-vendor before writing any new glue.
