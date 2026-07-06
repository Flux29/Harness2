# ADR-0021 — Delete the superseded generation; extract its two tested reusables; keep pgvector memory

**Status:** Proposed · 2026-07-06 · resolves plan step **6.5**
(`crit-dead-code-strata`) · **supersedes-in-code ADR-0005** (Planner→Generators→
Critics) and **ADR-0006** (pydantic-graph orchestration), completing the
supersession ADR-0011/ADR-0010 began; rules on the two fork-report vocabularies
and `memory_pg`'s schema roster as the plan directs.

## Context

eval-optimizer carries **two architectural generations plus one orthogonal
infrastructure layer**. Only the second generation is live; the first is the
"legacy strata" the critique flagged as "interleaved and importable from
everywhere."

**Generation 1 — Planner→Tree-of-Generators→Debate-Critics (ADR-0005), on
pydantic-graph (ADR-0006). Superseded by ADR-0011.** Modules (first-party
lines): `graph.py` (240), `loop.py` (160), `validate.py` (190, Docker-sandbox
validation), `agents.py` (126, the planner/generator/optimizer/evaluator
builders); manual entrypoints `graph_check.py`, `validate_check.py`,
`planner_check.py`, `generator_check.py`; and the `schema.py` models used ONLY
here — `ExecutionPlan`, `Candidate`, `Critique`, `RankedCandidate`,
`PipelineResult`, `CheckResult`, `ValidationResult`, plus the old fork-report
vocabulary `BranchResult`/`ForkReport`.

**Generation 2 — harness-native Live Run Forking (ADR-0011). LIVE.**
`forking.py` (313) + `fork_check.py`; `schema.HarnessForkReport` /
`HarnessBranchResult`; shared live utilities `config.py`, `models.py`,
`observability.py`. This is the only path the refactor's Phase-4/6 work
exercises and the only fork vocabulary Matrix B pins.

**Infrastructure — durable pgvector memory (ADR-0004). Orthogonal, LIVE.**
`memory_pg.py` (172) + `memory_check.py` + `infra/initdb`. NOT a superseded
generation: it is separate durable-memory infra with tests, and Phase 4.2
rewired its embedding client onto the shared retrying transport. Its
`KNOWN_AGENTS` roster (`optimizer, evaluator, memory, query, ingestion,
evaluation, system`) maps to `infra/initdb/01_init.sql` schemas.

**Two bindings hold Gen-1 code alive from the test suite** (the reason
Phase 0.1a deliberately did NOT exclude these files, deferring their fate to
here):
- `test_smoke.py` imports `agents.Verdict`.
- `test_validate.py` imports `validate.parse_artifact`.

**Pre-wired containment.** `parity/layer-rules.yml` already ships a dormant
Gate-5 rule `live-path-never-imports-legacy` (forbids importing
`eval_optimizer.legacy`), harmless until a `legacy/` package exists — the plan
armed the relocation option in advance. The dup-scan machine allowlist holds
exactly one first-party entry (5.1's dated, self-expiring history dual-write);
the two fork-report vocabularies are **class/field** duplication, which the
function-body scanner does not machine-match — they are an inventoried comment,
owned here.

## The pivotal question

Everything downstream follows from one roadmap call the refactor cannot make
for you (the 6.3 lesson: unshipped ≠ unwanted): **is the Planner→Generators→
Critics / pydantic-graph generation (ADR-0005/0006) genuinely superseded, or
deferred like the checkpoint UI?** ADR-0011 replaced its *fork-viability* role,
but the multi-generator/debate-critic *pattern* is a plausible future building
block, and the eval-optimizer README still documents `python -m
eval_optimizer.loop`, `graph`, `planner`, `generator` as entrypoints.

## Decision

**Extract-and-delete (the plan's option 3), contingent on affirming Gen-1 is
superseded.** Delete the dead generation; rescue only the two pieces that have
tests and a plausible future; keep the pgvector infrastructure untouched. If
instead the roadmap wants Gen-1 preserved-but-contained, the alternative is
relocation to `eval_optimizer/legacy/` behind the pre-wired Gate-5 rule (see
Alternatives) — a choice surfaced for approval before any code moves.

1. **Delete Gen-1:** `graph.py`, `loop.py`, `validate.py`, `agents.py`
   (builders), `graph_check.py`, `validate_check.py`, `planner_check.py`,
   `generator_check.py`, and the Gen-1-only `schema.py` models. Git history
   preserves every line (what Phase 0.1's filtered-but-real history bought).
   After deletion, sweep for newly-orphaned shared utilities (`runtime.py`,
   used only by the deleted `*_check` entrypoints) and delete if dead.
2. **Extract the two tested reusables** (Tier-2 relocations, byte-preserving,
   PR labeled `relocation` so the Gate-1 AST comparator runs):
   - `validate.parse_artifact` → new `artifacts.py` (the `# === path ===`
     parser; `test_validate.py` retargets its import). The plan names this the
     genuinely-reusable piece.
   - `agents.Verdict` → `schema.py` (a clean structured-output model beside the
     other data shapes; `test_smoke.py` retargets its import).
   Both moves become `relocations:` manifest entries; Gate 2 lint one verifies
   old-path-gone / new-path-present.
3. **Fork-report vocabularies (sub-ruling):** delete the old
   `BranchResult`/`ForkReport` (with `CheckResult`/`ValidationResult`). The
   inventoried first-party fork-report duplication is resolved; the sole
   remaining machine-allowlist entry is 5.1's dated dual-write, which expires
   on its own cutover and is not a 6.5-owned item. The first-party machine
   allowlist is therefore at its irreducible minimum (zero 6.5-owned dups).
4. **`memory_pg` roster (sub-ruling): keep as-is.** It is ADR-0004
   infrastructure, not a superseded generation; trimming the seven schemas to
   the post-pivot roster is a live-infra DB migration (`infra/initdb`) with
   zero benefit to this cleanup, and is recorded as a future infra decision,
   not folded in here.
5. **Gate-5 containment:** with Gen-1 deleted there is no `legacy/` to ban, so
   the dormant rule stays harmless; add a rule forbidding first-party code from
   re-importing the deleted module names (`eval_optimizer.graph|loop|validate|
   agents`), turning "no resurrection" into a permanent CI property — the
   enforceable form of the containment the critique found missing.
6. Mark ADR-0005 and ADR-0006 **Superseded (in code) by ADR-0021** inline
   (their decisions stand as history; the code implementing them is retired),
   mirroring how ADR-0010 reads.

## Alternatives

- **Relocate Gen-1 to `eval_optimizer/legacy/`** — the choice if the roadmap
  revives the debate-critic pattern. Every moved function must pass Gate-1 AST
  equality against its original; every move is a `relocations:` entry
  (old-path-gone/new-path-present); the pre-wired
  `live-path-never-imports-legacy` rule arms; and the fork-report pair must
  STILL be resolved (relocation does not satisfy the dup criterion — the
  vocabularies must merge or the old one go). More machinery, and it keeps code
  the plan bought git history specifically to be able to delete. Recommended
  only if Gen-1 has a named future.
- **Delete everything including the two reusables** — rejected: discards
  `parse_artifact` (tests + explicit "plausible future") and `Verdict` (tests,
  clean model) for no gain; extraction is cheap and keeps the suite green.

## Consequences

- The tree drops ~1,100 first-party lines of dead generation; the live surface
  is `forking`/`fork_check` + `config`/`models`/`observability`/`schema` +
  the `memory_pg` infra, each with a live purpose.
- `crit-dead-code-strata` flips to `removed` for the deleted modules and
  `changed` (via the `relocations:` block) for the two extractions, same
  commit; `test_smoke.py` and `test_validate.py` stay green against the new
  import paths — the behavioral proof the pieces survived intact.
- Gate 4: no 6.5-owned first-party duplicate remains. Gate 5: the
  no-resurrection rule is permanent. Gate 1: the two extractions AST-match
  their originals (PR labeled `relocation`).
- ADR-0005/0006 read as code-superseded; the ADR index and eval-optimizer
  README lose the retired entrypoints (docs-sync at exit gate 6).
- Reversible via git if the roadmap later revives Gen-1 — the extraction
  points (`artifacts.py`, `schema.Verdict`) are where it would re-attach.

## Implementation sketch (lands only after this ADR is Accepted)

New `artifacts.py` (moved `parse_artifact`, byte-preserved); `Verdict` moved
into `schema.py`; delete the eight Gen-1 modules + Gen-1-only schema models;
delete `runtime.py` if the orphan sweep confirms it dead. Retarget
`test_validate.py` → `eval_optimizer.artifacts`, `test_smoke.py` →
`eval_optimizer.schema`. `parity/manifest.yml`: `crit-dead-code-strata` →
`removed`/`changed` with the two `relocations:` entries; add the Gate-5
no-resurrection rule to `layer-rules.yml`. Annotate ADR-0005/0006. Trim the
eval-optimizer README entrypoint list. PR carries the `relocation` label so
Gate 1 runs. `uv run pytest -q` green; `uvx pyright src` clean (fewer excludes —
the ISSUE-2 legacy pyright excludes for `loop.py`/`graph.py` are deleted with
the files, closing ISSUE-2).
