# ADR-0018 — Shared-prefix test suite as the fork selection signal; merge threshold = all shared tests pass

**Status:** Accepted · 2026-07-05 · resolves plan step **6.1**
(`crit-fork-selection-metric`) and sub-decision **6.1a**
(`crit-merge-threshold` — the numeric definition of `any_viable`) · refines
**ADR-0011** (deterministic selection) and **ADR-0005** (deterministic-ranking
value); builds on **ADR-0017** (no judge on failure paths) and Phase 4/5 results.

## Context

ADR-0011's C5 engine selects the winning branch "deterministically by test
outcome." The critique's finding (`crit-fork-selection-metric`): **branches
author their own tests** — `BUILDER_INSTRUCTIONS` tells every branch to "write
all source files AND a pytest test suite" — so the selection signal is
self-graded. The open questions (plan 6.1/6.1a): what signal should rank
branches, and what threshold makes a branch mergeable / the plan "viable"?

What the refactor established, verified against the pinned vendor source
(f2224c5, `coordinator._run_tests_for_branch`):

1. **`test_pass_ratio` is binary, not a ratio.** The vendor runs
   `test_command` in a per-branch snapshot and returns `1.0` on exit 0, `0.0`
   on any non-zero exit, `None` on no-signal (spawn failure, timeout, no
   root_dir, overlay gone). Two consequences:
   - The plan's motivating fear — "`>0` merges a 1-of-10 branch as winner" —
     **cannot occur at the harness level**: pytest exits non-zero if any test
     fails, so a partial pass reports `0.0`.
   - The *actual* defects are sharper: (a) `1.0` means "the branch passed the
     suite the branch itself wrote" — a branch with one trivial test scores
     the maximum; and (b) ranking among multiple `1.0` branches is vacuous —
     `sorted(..., reverse=True)` is stable, so today's "deterministic
     selection" among all-passing branches reduces to **whichever approach was
     listed first**. Deterministic, yes; a ranking, no.
2. **The vendor gives us the pieces for a shared, integrity-checked suite
   without any vendor edit.** Branches inherit the parent work tree via the
   copy-on-write overlay (the "shared prefix"), and with
   `keep_artifacts=True` the `ForkMaterializer` mirrors every branch's file
   writes to disk under `<fork-dir>/branches/<label>/` alongside
   `<fork-dir>/parent/` (layout confirmed empirically by a prior run's
   artifacts in-repo). First-party code can therefore diff each branch's test
   files against the parent's after branches settle — offline and
   deterministic.
3. Post-Phase-4/5 posture: ADR-0017 removed the judge from failure paths;
   4.0's offline scaffolding (fake coordinator + full TestModel fork run) can
   pin whatever metric is chosen; 4.5's `selection_path` records provenance;
   5.2 gates all fork host-execution behind explicit configuration.

## Options weighed (the plan's four candidates)

- **(A) Fixed task-supplied suite injected into every branch — CHOSEN, in its
  practical form (below).** Removes the conflict of interest (author ≠
  examinee) instead of taxing it; deterministic; offline-testable.
- **(B) Shared held-out suite the branches never see** — rejected. Hiding the
  spec from a code generator measures luck, not viability: branches cannot aim
  at a contract they cannot read (normal TDD shows the tests). Its anti-gaming
  value is retained more cheaply by (A)+integrity: branches may *read* the
  suite but provably cannot *rewrite* it. Residual risk — overfitting to the
  visible suite — is accepted and recorded as the revisit trigger.
- **(C) Self-authored ratio + test-quality floor (assertion counts /
  mutation-lite)** — rejected. Floors on self-authored suites are gameable by
  construction and add analysis machinery while keeping the core defect: the
  examinee still writes the exam.
- **(D) Ratio filters, judge ranks among passers** — rejected. It would
  reintroduce the LLM judge onto the happy path immediately after ADR-0017
  removed it from the failure path, against ADR-0005/0011's deterministic
  mandate; it costs live tokens; and offline CI could never exercise ranking.
  If a future need to rank many passers outgrows the tie-break below, that is
  a new ADR, not a fallback.

## Decision

**6.1 — the selection signal is the binary pass of a SHARED test suite that
enters the fork exactly once, via the shared prefix, and is
integrity-verified per branch.**

1. **Provenance of the suite:** supplied by the caller when it has one (new
   optional `tests` input to `run_forked_viability`); otherwise authored by
   the **parent builder run before forking** ("write ONLY the pytest suite
   for this task into `tests/`, then stop"). Either way it exists in the
   parent work tree before `fork()`, so every branch inherits the identical
   suite through the copy-on-write prefix.
2. **Branches implement; they do not grade.** Branch steer changes to
   "implement so the existing `tests/` pass; do NOT modify `tests/`."
   `BUILDER_INSTRUCTIONS` loses the write-your-own-tests clause.
3. **Integrity check (the teeth):** the fork runs with `keep_artifacts=True`;
   after branches settle, first-party code compares each branch's
   materialized `tests/` against the parent's (`branches/<label>/tests/**` vs
   `parent/tests/**`, content hashes). A branch that altered, added to, or
   deleted from the suite is **disqualified** — treated as failing regardless
   of its reported ratio, and recorded on its `HarnessBranchResult` (additive
   field, Matrix B additive-only rule). Artifacts are cleaned up after the
   check.
4. **Deterministic tie-break, stated explicitly** (replacing the accidental
   first-listed-wins): among qualified passing branches, rank by
   `error_count` ascending, then `cost_usd` ascending (cheapest clean
   implementation wins), then original approach order as the final stable
   tie-break. No judge anywhere in selection.

**6.1a — the merge threshold, numerically:** a branch is mergeable iff its
**untampered shared-suite ratio == 1.0** (with the vendor's binary semantics:
the whole shared suite passed; if upstream ever reports granular ratios,
partial passes remain unmergeable without revisiting this ADR).
`any_viable := a branch met that bar and was merged.` `None`-signal branches
are never mergeable (unchanged), and — per ADR-0017 — infrastructure failures
raise rather than shape `any_viable`.

## Consequences

- `1.0` stops meaning "passed its own exam" and starts meaning "satisfied the
  one contract every sibling faced." Branch quality differences become
  visible in the signal instead of laundered by it.
- The accidental "first approach wins ties" behavior is retired for a stated,
  reproducible ordering; selection remains fully offline-testable (4.0's
  scaffolding pins it in CI).
- `keep_artifacts=True` replaces `False`: fork dirs exist on disk for the
  integrity check's duration (bounded cost; first-party cleanup after
  selection). The materialized artifacts also improve postmortems.
- Parity/manifest: `crit-fork-selection-metric` and `crit-merge-threshold`
  flip with the implementation; Matrix B `test_pass_ratio` row changes
  **semantics only** (field shape identical, exactly as the plan's Matrix B
  anticipated), `any_viable` row gets its 6.1a definition, plus one additive
  disqualification field.
- Known residual risks, accepted: branches can overfit to the visible suite
  (revisit trigger: winners that pass the suite but fail in use); the parent-
  authored suite's quality bounds the signal's meaning (mitigated by it being
  authored once, unforked, by a model with no stake in any branch — and
  callers with real suites can inject them).
- Cross-reference for ADR **6.4** (security posture): the vendor test runner
  inherits the **full parent environment** (its own documented SECURITY
  caveat) — 5.2's `EVALOPT_ALLOW_HOST_EXEC` gate is the current control;
  6.4 should weigh environment scrubbing for `test_command`.

## Implementation sketch (lands only after this ADR is Accepted)

`forking.py`: parent prompt becomes suite-authoring (or writes caller-supplied
`tests`); steers updated; after `_wait_for_branches` + `branch_outcomes`, run
the tests/-integrity check, disqualify tamperers, rank
`(ratio == 1.0 ∧ qualified, error_count asc, cost_usd asc)`, merge the top or
`abort_fork()`. `schema.py`: additive disqualification field on
`HarnessBranchResult`. Tests: fake-coordinator suite covers tamper/clean/
threshold/tie-break; the full-TestModel E2E pins the new threshold; a
FunctionModel E2E tampers through real overlays; Matrix B field-compare
unchanged. Same-commit manifest flips for both findings, per Gate 2.

**Implementation note (at acceptance, 2026-07-05):** the integrity check landed
on the vendor's **public `build_diff_report` API over the live overlays**
instead of the sketched `keep_artifacts=True` + on-disk artifact diff. During
implementation the materializer source showed `flush_delete` leaves no trace
when a branch deletes a parent file it never wrote — the artifact mirror
cannot see the strongest tamper vector (deleting shared tests), while the diff
API's end-state classification (`created/modified/deleted/untouched`) can.
Same decision, stronger mechanism, no disk artifacts to clean up
(`keep_artifacts` stays `False`); the check runs before merge/abort release
the overlays. Protected set: `tests/**` plus root `conftest.py`, `pytest.ini`,
`pyproject.toml`, `setup.cfg`, `tox.ini` (pytest-rerouting configs).
