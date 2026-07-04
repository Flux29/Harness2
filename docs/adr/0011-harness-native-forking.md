# ADR-0011 — Adopt harness-native Live Run Forking for C5

**Status:** Accepted · 2026-06-30 · **Supersedes ADR-0010** (graph-level forking spine);
corrects ADR-0008 (under-weighted harness forking); refines ADR-0007.

## Context
The first `fork_check` run failed (all branches non-viable, ~22 min, 48 model calls) —
diagnosed in `docs/C5_FAILURE_DIAGNOSIS.md`: the Generator is a `create_deep_agent`
autonomous agent that *did the task with tools* (wrote files into its own workspace,
ran commands, spawned subagents) and returned a transcript, not the `# === path ===`
text our pipeline parses.

While diagnosing, we read `pydantic-deepagents/docs/advanced/forking.md` and found the
harness ships **Live Run Forking** — a complete, programmatically-drivable
fork → branch → test → select engine:
- `create_deep_agent(forking=True, include_checkpoints=True)` or a tuned
  `LiveForkCapability(max_branches=…, max_depth=…, test_command="pytest -q", test_timeout_s=…)`.
- Programmatic driver: after a parent `agent.run(...)`, `deps.fork_coordinator.fork([BranchSpec(label, steer), …], parent_history=…, isolation=BranchIsolation())`.
- Copy-on-write branch isolation (each branch writes to its own overlay; winner flushes
  to parent on merge, losers discarded), per-branch + aggregate **`budget_usd`**,
  `inspect_branches`, `diff_branches`, `fork_cost`, and `merge_or_select("pick:<id>" | "auto" | "vote" | "abort")`.
- A `test_command` runs per branch and feeds a `test_pass_ratio` into selection.

Our `forking.py` + `validate.py` + `Rank` substantially reinvented this. The ADR-0008
audit called harness forking an "optional interactive layer" and under-weighted it — a
miss; it is a programmatic POC engine.

## Decision
**Adopt harness-native Live Run Forking as the C5 engine.**
- Build the deep agent with forking enabled and a `test_command` (`pytest -q`).
- Drive it **programmatically**: the parent run produces the frozen plan; then
  `coordinator.fork([...])` spawns one branch per approach (each `BranchSpec.steer`
  carries the approach); wait via `inspect_branches`; **select deterministically by
  test outcome** with `merge_or_select("pick:<id>")` — NOT the LLM `auto`/`vote` judge
  (preserves the deterministic-ranking value of ADR-0005).
- Set per-branch and aggregate **budgets** so a runaway branch can never repeat the
  22-min/48-call burn.
- **Retire** most of custom `forking.py` and the sandbox in `validate.py`; keep
  `parse_artifact` only if still needed, and optionally keep the Docker validator as a
  post-hoc verifier of the winner (see trade-off 1).

## Consequences
- Far less custom code; native budgets (cost), CoW overlays + auto-discard (file
  hygiene — the winner flushes, losers vanish), `diff_branches`/`fork_cost` for free.
- **The Generator fix is architectural, not "make it tool-less."** In Path B the
  generator *should* use tools (it writes files to its overlay); we read/test those
  files instead of parsing `.output`. So ADR-0007 ("keep the harness") stands; the real
  error was misusing the harness rather than using its forking feature.
- **Trade-off 1 — isolation.** `test_command` runs against each branch's *materialised
  tree on the host* (`LocalBackend`), i.e. generated code executes on the machine, not
  in our `--network none` Docker sandbox. Accepted for a local POC; optionally re-add
  Docker isolation later or Docker-verify only the winner. **Documented safety downgrade.**
- **Trade-off 2 — determinism.** We use manual, test-ratio-based selection, not the
  judge, to keep runs reproducible.
- **Supersedes ADR-0010** (custom graph-level forking spine). Open item for the PDR
  rewrite: reconcile the role of the pydantic-graph control plane (ADR-0006/0008) now
  that the fork-viability inner loop is harness-native — the graph may remain the
  top-level orchestrator or C5 may run standalone.

## Validation (when implemented)
1. `fork_check` completes in minutes, not tens of minutes; branch budgets visible.
2. At least one branch reports passing tests; the winner is selected by test ratio.
3. Logfire shows the fork coordinator + branch runs; no unbounded tool-loop.
4. No stray files left on disk (losers discarded; winner in a known, cleaned location).
