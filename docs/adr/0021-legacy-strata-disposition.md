# ADR-0021 — Relocate the deferred generation to committed `legacy/`; extract its two tested reusables; keep pgvector memory

**Status:** Accepted · 2026-07-06 · resolves plan step **6.5**
(`crit-dead-code-strata`) · marks **ADR-0005** (Planner→Generators→Critics) and
**ADR-0006** (pydantic-graph orchestration) **Deferred, not Superseded** —
their integration is paused, their substrate preserved.

## Context

eval-optimizer carries **two architectural generations plus one orthogonal
infrastructure layer**. Only the second is live; the first is deferred, not
dead — a distinction that governs everything below.

**Generation 1 — Planner→Tree-of-Generators→Debate-Critics (ADR-0005), on
pydantic-graph (ADR-0006). Integration DEFERRED (not superseded).** Modules
(first-party lines): `graph.py` (240), `loop.py` (160), `validate.py` (190,
Docker-sandbox validation), `agents.py` (126, the planner/generator/optimizer/
evaluator builders); manual entrypoints `graph_check.py`, `validate_check.py`,
`planner_check.py`, `generator_check.py`; the `schema.py` models used ONLY here
(`ExecutionPlan`, `Candidate`, `Critique`, `RankedCandidate`, `PipelineResult`,
`CheckResult`, `ValidationResult`, and the old fork vocabulary `BranchResult`/
`ForkReport`, plus the `DIMENSIONS`/`DIMENSION_WEIGHTS` constants). `graph.py`
is a **working pydantic-graph scaffold** — real `Plan→Generate→Criticize→Rank→
Validate` `BaseNode`s and a real weighted-scoring matrix in `Rank`, with the LLM
nodes deterministically stubbed behind `# TODO(C)` markers pending the real
Planner/Generators/Critics. It is a deferred integration substrate whose stated
purpose is to raise documentation-retrieval accuracy and output quality and cut
token cost by turning recognized non-deterministic model behavior into
deterministic graph nodes.

**Generation 2 — harness-native Live Run Forking (ADR-0011). LIVE.**
`forking.py` (313) + `fork_check.py`; `schema.HarnessForkReport` /
`HarnessBranchResult`; shared live utilities `config.py`, `models.py`,
`observability.py`.

**Infrastructure — durable pgvector memory (ADR-0004). Orthogonal, LIVE.**
`memory_pg.py` (172) + `memory_check.py` + `infra/initdb`. NOT a generation.

**Two bindings keep Gen-1 code alive from the test suite** (the reason
Phase 0.1a deliberately did not exclude these files, deferring their fate
here): `test_smoke.py` → `agents.Verdict`; `test_validate.py` →
`validate.parse_artifact`.

**Is Gen-2 a functional replacement for Gen-1?** No — a deliberate
substitution, not an equal. Gen-2 represents **Planner** (parent plan run) and
**Tree-of-Generators** (branch-per-approach) structurally, but ADR-0017/0018
replaced the **Debate-Critics'** multi-dimensional weighted LLM scoring
(correctness/architecture/performance) with a **binary shared-test-suite pass**
plus a deterministic tie-break, removing the judge entirely. The forking engine
cannot score the architecture/performance dimensions at all, and no data shows
its selection matches or exceeds critic-scored quality (the critic path was
never run — its nodes are stubbed). Supersession is therefore unjustified;
preservation is correct.

**Governing policy: agentic deletion is disabled.** `.gitignore` records it
(*"Parked-instead-of-deleted files (agentic deletion is disabled by policy)"*),
README/PDR restate it. The critique named keeping the strata live-importable
"a policy violation by the policy's own author," pointing to parking — not
deletion — as the fix. An earlier draft of this ADR recommended deletion
(anchored on the plan's option-1 wording, *"git history now preserves them"*);
that conflicts with the standing policy, and the policy wins.

## Decision

**Relocate Gen-1 to a committed, import-quarantined `eval_optimizer/legacy/`;
extract its two tested reusables to live homes; keep pgvector memory. Nothing
is deleted.** Two preservation *tiers* are made explicit (policy refinement):

- **`Obsolete/`** — genuinely dead, deletion-bound files: local-only,
  git-ignored, never-pushed (unchanged; the existing policy).
- **`legacy/`** — deferred-with-a-named-future substrates: **committed**,
  push- and clone-durable, out of the live import path, contained by the
  Gate-5 rule `live-path-never-imports-legacy` (already pre-wired in
  `layer-rules.yml`). Gen-1 is this tier: it has a future (above), so it earns
  push-durable, CI-enforced preservation rather than one machine's local disk.

1. **Extract the two tested reusables to LIVE homes first** (byte-preserving
   Tier-2 relocations; PR labeled `relocation` so the Gate-1 AST comparator
   proves they are unchanged):
   - `validate.parse_artifact` → new `artifacts.py` (`test_validate.py`
     retargets its import). The plan's named genuinely-reusable piece.
   - `agents.Verdict` → `schema.py` (`test_smoke.py` retargets its import) —
     a clean structured-output model beside the live data shapes.
2. **Relocate the rest of Gen-1 to `eval_optimizer/legacy/`**, carrying its
   own schema models (`legacy/schema.py`) so live `schema.py` holds only the
   `Harness*` models + extracted `Verdict` — resolving the critique's
   live/dead interleaving. `runtime.py` moves too if the post-move orphan
   sweep confirms it is Gen-1-only.
3. **Fork-report vocabularies (sub-ruling):** the old `BranchResult`/
   `ForkReport` (+ `CheckResult`/`ValidationResult`) move to `legacy/schema.py`.
   The two vocabularies no longer coexist in the live tree — the inventoried
   first-party fork-report duplication is resolved by removal from the live
   import path (not by deletion).
4. **`memory_pg` roster (sub-ruling): keep as-is.** ADR-0004 infrastructure,
   not a generation; trimming the seven schemas is a live-infra DB migration
   with no cleanup benefit — recorded as a future infra decision, not folded
   in here.
5. **Containment:** the pre-wired Gate-5 `live-path-never-imports-legacy` rule
   arms the moment `eval_optimizer/legacy/` exists — the enforceable form of
   the containment the critique found missing. `legacy/` may import live
   utilities (config/models/schema/artifacts); the live path may never import
   `legacy/`.
6. **ADR-0005/0006 → Deferred** (annotated inline; decisions and substrate
   preserved), not Superseded.
7. **The built agentic system's own deletion surfaces** (`LocalBackend`/console
   `delete_file`, fork-overlay discards) **stay as-is** — a deliberate call to
   keep the vendor tree pristine and the runtime hygienic; the park-don't-delete
   rule governs *this repository's* first-party tree and the refactor agent, not
   the harness's runtime file tools.

## Consequences

- No first-party line is deleted; ~1,100 lines of Gen-1 leave the *live import
  path* into committed `legacy/`, preserved and clone-durable.
- `crit-dead-code-strata` flips to `changed` with the `relocations:` block;
  `test_smoke`/`test_validate` stay green against the new live import paths —
  the behavioral proof the extracted pieces survived intact. Gate 1 AST-matches
  every moved symbol (PR labeled `relocation`); Gate 2 verifies each
  relocation's old-path-gone / new-path-present; Gate 5 enforces the layer ban;
  Gate 4's first-party fork-report inventory item is resolved.
- **Gate-1 comparator fix (in this change):** `relocations:` was empty since
  Phase 0, so `ast_equal.py`'s old-path resolver — which probed the *working
  tree* — had never run against a genuinely-moved (vanished) old path and would
  crash on one. Fixed to resolve the old module from the *base blob*. First
  relocation to exercise the gate; the fix is what makes the gate real.
- ISSUE-2 closes: the legacy pyright excludes (`loop.py`/`graph.py`) are
  re-owned by this ADR as a single `legacy/` exclude (deferred code stays out
  of the typed live path — the resolution ISSUE-2 anticipated).
- ADR-0005/0006 read as Deferred; the eval-optimizer README's retired
  entrypoints move under a `legacy/` note (docs-sync).
- `CLAUDE.md` gains the no-deletion / park-or-quarantine rule as a numbered
  standing rule (it lived only in a `.gitignore` comment and prose).

## Alternatives rejected

- **Delete Gen-1** (the earlier draft) — violates the standing no-deletion
  policy; discards a deferred substrate with a named future.
- **Park Gen-1 to gitignored `Obsolete/`** — honors the policy literally but
  is local-only: a fresh clone loses the substrate, Gate 5 can enforce nothing
  on absent files, and it recreates the clone-provenance gap the critique
  flagged for the vendor `.git`. `Obsolete/` stays reserved for genuinely dead,
  deletion-bound files; a deferred-with-future substrate belongs in committed
  `legacy/`.

## Implementation sketch

New live `artifacts.py` (moved `parse_artifact`, byte-preserved) and live
`schema.Verdict`; new `eval_optimizer/legacy/` package holding `graph.py`,
`loop.py`, `validate.py` (minus `parse_artifact`), `agents.py` (minus
`Verdict`), the four `*_check` entrypoints, `legacy/schema.py` (the Gen-1
models), and `runtime.py` if orphaned. Retarget `test_validate.py` →
`eval_optimizer.artifacts`, `test_smoke.py` → `eval_optimizer.schema`. Fix
`parity/ast_equal.py` base-path resolution. `parity/manifest.yml`:
`crit-dead-code-strata` → `changed` with a `relocations:` map of every moved
public symbol. `pyproject.toml`: pyright exclude `src/eval_optimizer/legacy`
(replaces the two file excludes; closes ISSUE-2). `CLAUDE.md`: standing rule.
Annotate ADR-0005/0006. Trim the eval-optimizer README entrypoint list. PR
carries the `relocation` label so Gate 1 runs. Green: `uv run pytest -q`,
`uvx pyright src`, all gates.
