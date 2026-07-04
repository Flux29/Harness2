# AgenticWork Harness — Fix Plan

Date: 2026-07-01
Author: review pass responding to `docs/AGENTICWORK_HARNESS_CRITIQUE.md`
Scope: repair plan only — no source edits made in this pass.
Evidence base: live inspection of the workspace + installed `pydantic_deep 0.3.34`
in `projects/eval-optimizer/.venv`.

---

## 0. What this plan is

The critique is accurate on its material points. This document turns it into a
prioritized, file-level repair plan. It is organized into three tiers by risk and
effort:

- **Tier 1 — Correctness & consistency.** Make the workspace tell one true story
  and pass its own tests. Low risk, no change to harness behavior.
- **Tier 2 — Code hardening.** Remove the private-API dependency, add tests that
  cover the architectural claims, narrow tool surfaces, wire security.
- **Tier 3 — Absent capability surfaces.** TUI, DeepResearch, teams, MCP, browser,
  liteparse. Each is effectively a new sub-project.

Two decisions are already made for this plan:
1. **Fork selection** moves to the shipped public `resolve()` path (see Fix 2.1).
2. This pass produces the plan only; implementation is gated on your go-ahead per
   tier.

---

## 1. Verification notes (what was confirmed, and two refinements)

Confirmed against the filesystem and installed package:

- **Failing test is real and its cause is exactly as the critique states.**
  `config.py` calls `load_dotenv()` at import and defaults `GLM_MODEL` to
  `z-ai/glm-5.1`; `.env` contains `GLM_MODEL=z-ai/glm-5.2`. `test_settings_defaults`
  sets only `NVIDIA_API_KEY`, so the real `.env` value leaks in and the assertion
  `s.glm_model == "z-ai/glm-5.1"` fails.
- **Model default drifts across five files:** `config.py` (5.1), `.env.example` (5.1),
  project `README.md` (5.1), `.env` (5.2), root `PDR.md` (5.2).
- **`forking.py` depends on a private method.** `coordinator._build_branch_outcomes()`
  is underscore-private in `pydantic_deep/features/forking/coordinator.py`. The
  public surface (`inspect_branches()` → `BranchStatus`, `merge_or_select`,
  `fork_cost`) does **not** expose per-branch `test_pass_ratio`; only `resolve()`
  reads it internally.
- **Doc conflicts confirmed.** `PDR.md` ("verified working"), project `README.md`
  (old two-agent loop), `C5_FORK_PLAN.md` (graph-level spine), ADR-0010, and
  ADR-0011 (supersedes 0010) coexist without reader-facing status banners on the
  superseded docs. `C5_FAILURE_DIAGNOSIS.md` and ADR-0011 encode opposite lessons.
- **`scaffolds/` and `notebooks/` are empty**; TUI, DeepResearch, teams, browser,
  MCP wiring, and liteparse have no local implementation.

Two refinements to the critique (both help us):

- **Refinement A — switching to the public judge does *not* discard the test
  signal.** Because `forking.py` sets `test_command="pytest -q"`, the harness runs
  each branch's tests and threads `test_pass_ratio` into the judge, which weights it
  at `0.4` (`features/forking/judge.py`). So the "deterministic vs judge" tension the
  critique flags (matrix row *AI judge / merge modes*, and Q2) is narrower than it
  looks: the public path still selects primarily on tests. This makes Fix 2.1 low-cost.
- **Refinement B — the tests cannot be run in this environment.** The project
  `.venv` is Windows-native (`.venv/Scripts/python.exe`); it can't execute in the
  Linux sandbox. The failing test was confirmed by static analysis of the load
  order, not by re-running pytest. Fixes below are written to be verified on your
  Windows machine with `uv run pytest`.

---

## 2. Tier 1 — Correctness & consistency (do first)

### Fix 1.1 — Make `test_settings_defaults` deterministic and pick one model default

Addresses critique **Q4, A4, C1**.

Problem: the test asserts a hardcoded default while `load_dotenv()` imports the real
`.env`. Two things are wrong — the test isn't isolated, and the codebase has no
single source of truth for the model.

Recommended actions:

- **Decide the canonical default = `z-ai/glm-5.2` via OpenRouter** (matches `.env`,
  `PDR.md`, and the actual runtime). Then:
  - `config.py`: change the `GLM_MODEL` fallback from `z-ai/glm-5.1` to `z-ai/glm-5.2`.
  - `.env.example`: change `GLM_MODEL` to `z-ai/glm-5.2` and update the per-role
    override examples to the 5.2 slugs.
  - project `README.md`: replace "GLM 5.1" references with 5.2 and update the
    Phase 1/2 framing (see Fix 1.2).
- **Make the test hermetic** so it stops depending on ambient env / `.env`:
  - In `test_settings_defaults`, explicitly `monkeypatch.delenv("GLM_MODEL", raising=False)`
    (and any other keys it asserts defaults for) before calling `from_env()`, then
    assert against the new canonical default.
  - Optionally, guard `load_dotenv()` in `config.py` so tests can suppress it, e.g.
    `load_dotenv(override=False)` is already the effective behavior, but the deeper
    fix is to not let `.env` decide a *default-value* test — the monkeypatch above
    is the minimal correct fix.

Files: `src/eval_optimizer/config.py`, `.env.example`, `tests/test_smoke.py`,
`projects/eval-optimizer/README.md`.
Risk: low. Verify: `uv run pytest` → 7/7 on Windows.

### Fix 1.2 — Reconcile the project README with the active architecture

Addresses **C2**. The README still sells the two-agent evaluator-optimizer loop as
the entrypoint. Rewrite its header and "run the loop" section to state that the
active path is C5 harness-native forking (`fork_check.py` → `forking.py`), and
demote the `loop.py` walkthrough to a "legacy / reference pipeline" subsection that
mirrors the "Legacy / superseded" table already in `PDR.md`.

Files: `projects/eval-optimizer/README.md`. Risk: low (docs only).

### Fix 1.3 — Soften the PDR's "verified working" claim to match evidence

Addresses **C1**. No automated test currently exercises `run_forked_viability()`,
and the one recorded live run (`C5_FAILURE_DIAGNOSIS.md`) ended with all branches
non-viable. Change "ADR-0011, verified working" to something evidence-true, e.g.
"ADR-0011, active path — one live run recorded (all branches non-viable, see
`C5_FAILURE_DIAGNOSIS.md`); automated coverage pending (Fix 2.2)." Re-promote to
"verified" only after Fix 2.2 lands a passing run.

Files: `PDR.md`. Risk: low.

### Fix 1.4 — Add obsolescence banners to superseded C5 docs

Addresses **C3, C4**. The superseded docs read as if current. Add a one-line
front-matter banner at the top of each:

- `docs/C5_FORK_PLAN.md` → `> SUPERSEDED by ADR-0011. Retained for history; graph-level forking is no longer the spine.`
- `docs/adr/0010-fork-based-plan-viability.md` → already says "Accepted" but is
  superseded by 0011; add `> Superseded by ADR-0011.`
- `docs/C5_FAILURE_DIAGNOSIS.md` → add a closing "Resolution" note pointing to
  ADR-0011 so the "tool-less emitters" conclusion isn't read as current guidance.

Files: the three docs above. Risk: none (docs only).

### Fix 1.5 — Reconcile package naming once, centrally

Addresses **A1**. Add a short "Names" note to `PDR.md` (or the top-level README):
repository/docs = `pydantic-deepagents`; PyPI install = `pydantic-deep`; Python
import = `pydantic_deep`; pinned version = `0.3.34`. Reference it instead of
re-explaining per file.

Files: `PDR.md`. Risk: none.

### Fix 1.6 — Stop committing disposable artifacts

Addresses **Q8, C7**. The tree carries `.pytest_cache/`, `.hypothesis/`, and a live
`.pydantic-deep/forks/<uuid>/…` fork tree. `.gitignore` already covers the caches;
add `.pydantic-deep/` (fork overlays) to the project `.gitignore`, and add a root
`AgenticWork/.gitignore` (currently none) covering `__pycache__/`, `*.pyc`,
`.pytest_cache/`, `.hypothesis/`, and `.venv/`. Then `git rm -r --cached` the
already-tracked artifacts.

Files: `projects/eval-optimizer/.gitignore`, new `AgenticWork/.gitignore`.
Risk: low; verify `git status` is clean of caches afterward.

---

## 3. Tier 2 — Code hardening

### Fix 2.1 — Replace the private `_build_branch_outcomes()` call with the public `resolve()` path  ✅ decision made

Addresses **Q1, Q2**, and the matrix *AI judge / merge modes* row.

Current `forking.py` reaches into `coordinator._build_branch_outcomes()` to rank
branches by `test_pass_ratio`, then calls the public `merge_or_select("pick:<id>")`,
with a `resolve(auto)` fallback. The private call is the maintenance risk.

Planned change — use only the shipped public contract:

- Delete the `_build_branch_outcomes()` block. Call
  `outcome = await coordinator.resolve(strategy=MergeStrategy(kind="auto"))`
  (or `kind="auto_with_fallback"` if you want the confidence gate). Because
  `test_command` is set, the judge already weights `test_pass_ratio` at 0.4, so
  selection stays test-driven — see Refinement A.
- Read results off the **public** `ResolveOutcome`: `outcome.merge_result`
  (`winner_branch_id`, `applied_paths`, …) and `outcome.verdict` /
  `outcome.effective_confidence` for the report.
- Populate per-branch report rows from **public** sources only:
  `coordinator.inspect_branches()` (`BranchStatus`: id, label, state, turn,
  preview) joined with `coordinator.fork_cost()` (`ForkCostSummary` /
  `BranchCost`: `cumulative_usd`, `budget_usd`, `remaining_usd`). Note
  `BranchStatus` does **not** carry `test_pass_ratio`; if you need the exact
  ratio in the report, capture it from `outcome.signals.test_pass_ratio` for the
  winner and mark losers as "not surfaced by public API" rather than reaching back
  into the private method.
- Update `HarnessForkReport` / `HarnessBranchResult` in `schema.py` to match the
  public fields actually available (drop fields that only the private outcome
  exposed, add `confidence` and cost fields).
- Update the ADR-0011 "deterministic test-ratio selection" language to
  "judge-assisted selection with `test_pass_ratio` weighted 0.4" so the documented
  contract matches the code.

Files: `src/eval_optimizer/forking.py`, `src/eval_optimizer/schema.py`,
`docs/adr/0011-harness-native-forking.md`.
Risk: medium (behavioral: selection now judge-assisted, but still test-weighted).
Verify: a live `fork_check.py` run on a task with one obviously-correct branch
selects that branch; feeds Fix 2.2.

### Fix 2.2 — Add tests that cover the architectural claims

Addresses **Q3, C1**. Today's tests cover only `Verdict`, settings, and the
validator. Add, at minimum:

- `models.py`: unit tests for `build_model()` prefix routing
  (`openrouter:` / `ollama:` / `anthropic:` / bare NVIDIA) — assert the right
  provider/base_url is selected, mocking network. Pure-logic, offline.
- `forking.py`: a test that runs `run_forked_viability()` against a trivial task
  using a **stub/fake model** (pydantic-ai `TestModel`/`FunctionModel`) so it needs
  no API key, asserting a winner is chosen and losers discarded. This is the test
  that lets Fix 1.3 restore "verified."
- `schema.py`: round-trip tests for `HarnessForkReport` after the Fix 2.1 field
  changes.

Files: `tests/`. Risk: low. Verify: `uv run pytest`.

### Fix 2.3 — Narrow agent tool surfaces explicitly

Addresses **A7**. `create_deep_agent` defaults enable filesystem, subagents, plan,
memory, web search/fetch, monitoring, etc. The earlier C5 failure was partly a
too-broad-surface problem. For each builder in `agents.py` and the builder in
`forking.py`, pass explicit `include_*` toggles (turn off what the role doesn't
need) rather than relying on defaults. Document the intended surface per role in a
short comment block.

Files: `src/eval_optimizer/agents.py`, `src/eval_optimizer/forking.py`.
Risk: medium (behavioral); pair with Fix 2.2 so regressions are caught.

### Fix 2.4 — Wire a harness-native security hook

Addresses **Q7**. `rules/hooks/agentic_pre_tool_use.py` is a Codex-style hook not
connected to any deep agent. Either (a) pass `pydantic_deep.default_security_hook()`
(confirm exact export) into the builders' `hooks=` argument, or (b) adapt the
existing pip-block logic into a harness hook and register it. Document which agents
run under host execution (`LocalBackend(enable_execute=True)` in `forking.py`) and
what the hook guarantees.

Files: `forking.py`, `agents.py`, `rules/hooks/`. Risk: medium.

### Fix 2.5 — Resolve the host-vs-sandbox execution ambiguity

Addresses **Q6, matrix Docker-sandbox row**. `validate.py` + `infra/sandbox/Dockerfile`
describe network-disabled sandbox execution; `forking.py` runs `pytest` host-side.
Pick the intended story for the active path and state it in one place (PDR + ADR-0011):
either mark the Docker sandbox as legacy (consistent with the PDR's legacy table)
or make `forking.py` route test execution through the sandbox. Recommended: mark
sandbox legacy now, keep host execution behind the Fix 2.4 hook, and file sandbox
re-integration as a Tier 3 item.

Files: `PDR.md`, `docs/adr/0011-*`, optionally `forking.py`. Risk: low if docs-only.

---

## 4. Tier 3 — Absent capability surfaces (scope as separate sub-projects)

These are genuine feature builds, not fixes. Listed so the backlog is complete; each
should get its own ADR before implementation.

- **TUI readiness** (matrix, §7). Add a documented `pydantic-deep tui` entrypoint,
  a model/profile config, tool-approval policy, and a smoke check that the CLI
  launches against this workspace. Verify the CLI extra is actually installed.
- **DeepResearch app.** No local app exists. This is the largest item: web UI,
  planner + parallel research subagents, search-provider wiring (Tavily/Brave/Jina),
  report export, sandbox execution. Scope as its own project under `projects/`.
- **Teams / message bus** (`include_teams=True`), **MCP server wiring** (beyond the
  Logfire remote MCP mentioned in ADR-0009), **browser automation** (Playwright),
  **liteparse** document parsing, and **durable checkpoints** (replace
  `InMemoryCheckpointStore()` with a persistent store + a rewind/fork-from-checkpoint
  demo). Each: one ADR + one verification script, mirroring the existing
  `*_check.py` pattern.
- **Cost-tracking validation** (**A5**). Add a check that asserts token/USD
  accounting and budget-exceeded behavior for GLM 5.2 pricing via `fork_cost()`.
- **Catalog depth** (**C6**) and **scaffolds/notebooks** (**C7**). Once the above
  land, extend `catalogs/*.yml` with the concrete harness decisions (fork mode,
  security hook, model fallback policy, TUI/DeepResearch requirements) and populate
  `scaffolds/` + `notebooks/` so the "check AGENTIC_SCAFFOLDS first" workflow has
  real assets.

---

## 5. Suggested order of execution

1. **Fix 1.1** (green test suite) — unblocks everything and restores trust in `pytest`.
2. **Fixes 1.2–1.6** (one consistent story, clean tree) — cheap, high signal.
3. **Fix 2.1 + 2.2** (public API + a forking test) — removes the top maintenance
   risk and lets 1.3 restore "verified working."
4. **Fixes 2.3–2.5** (surface narrowing, security, execution story).
5. **Tier 3** items, each behind its own ADR, in priority order you choose.

## 6. Definition of done for Tiers 1–2

- `uv run pytest` in `projects/eval-optimizer` is 7/7+ green on Windows, hermetic.
- `grep` for `glm-5.1` returns only intentional historical references.
- No underscore-prefixed `pydantic_deep` attributes are referenced in `src/`.
- Every superseded doc carries a status banner; PDR/README/ADR-0011 agree on the
  active path and the model default.
- No cache/fork artifacts tracked by git.
