# ADR-0017 — Selection failures abort the fork, fail-loud (judge fallback retired from the programmatic path)

**Status:** Accepted · 2026-07-05 · resolves plan step **6.2** (`crit-silent-judge-fallback`
policy half; the observability half landed in Phase 4.5) · refines **ADR-0011**
(deterministic-selection mandate); informed by Phase 4 evidence (4.0, 4.5, 4.6,
`disc-abort-action-unsupported`).

## Context

ADR-0011 mandated **deterministic selection by test outcome** for the C5 viability
engine — "NOT the LLM `auto`/`vote` judge." The implementation nevertheless wrapped
deterministic selection in a bare `except Exception:` that silently fell back to
`resolve(strategy=MergeStrategy(kind="auto"))` — an LLM judge that picks and merges a
winner. The open question (plan 6.2): on an exception in deterministic selection,
should the engine (a) fall back to the judge (v1 behavior), (b) abort the fork
fail-loud, or (c) retry deterministic once, then abort?

The refactor was sequenced so this decision would be made with data. What Phase 4
produced:

1. **Every known firing of the fallback was a masked programming error, zero were
   transient faults.** The exit-gate fork-timeout E2E test (enabled by 4.5's logging)
   surfaced `disc-abort-action-unsupported`: v1's own *abort* path called
   `merge_or_select("abort")` — an action the pinned coordinator (f2224c5) does not
   accept — so the `ValueError` fell into the bare except and **the judge quietly
   merged a winner on a path whose stated intent was "no branch passed, abort."**
   `any_viable` could read `True` with zero passing branches. Notably, ADR-0011's
   Context section itself recorded the vendor docs' promise of an `"abort"` action;
   the coordinator never implemented it. The fallback did not absorb environmental
   flakiness — it converted upstream API drift into a silent behavior inversion and
   hid it for the repo's entire life.

2. **The failure taxonomy leaves no class the judge (or a retry) serves.** Post-4.x,
   infrastructure trouble in the deterministic path does not raise: the vendor's
   `branch_outcomes()` reports `test_pass_ratio=None` on runner-disabled, missing
   `root_dir`, released overlay, spawn failure, or test timeout — and `None` flows
   through the `>0` threshold into the abort branch *without* an exception. Transient
   HTTP faults are retried at the transport layer (ADR-0008). What remains as an
   actual *exception* here is API drift and programming error — precisely the class a
   retry re-raises slower and a judge actively hides.

3. **The fallback's product is already worthless on this path.** Since 4.6,
   `save_winner_dir` materializes only deterministic winners, so a judge-fallback
   "winner" is an id whose artifacts the caller can never obtain. Since 4.5, the
   fallback also costs live judge-model calls (money; impossible offline — the CI
   suite runs TestModel only) to produce it.

4. `any_viable` is about to become a load-bearing signal: ADR 6.1/6.1a will define the
   selection metric and merge threshold on top of it. A fallback that can mint winners
   on failure paths poisons exactly the data 6.1 needs.

## Decision

**Option (b): abort the fork and fail loud.** On any exception in deterministic
selection, `run_forked_viability`:

1. logs the exception with traceback (4.5's warning event stays — Matrix E's declared
   `E:errors` row);
2. calls `coordinator.abort_fork()` (the real abort API, per the Phase 4 fix):
   cancel every branch task, release overlays, merge **nothing**;
3. **re-raises the original exception to the caller.** A selection failure is an
   infrastructure/programming error, not evidence about the plan — it must never be
   encoded as `any_viable=False` (which 6.1a will read as "plan not viable"), and
   never as a judge-minted winner. The existing `finally` (aclose + workdir cleanup)
   still runs.

Scope and residuals:

- `resolve()` / `MergeStrategy` / the judge leave `forking.py` entirely. The judge
  remains available in the vendor harness for interactive and agent-driven flows
  (`fork_run` tool, `auto`/`vote` strategies); this ADR governs only eval-optimizer's
  **programmatic viability path**, where ADR-0011's deterministic mandate applies.
- `HarnessForkReport.selection_path` keeps its `Literal["deterministic",
  "judge_fallback"] | None` shape for schema stability (Matrix B additive-only);
  `"judge_fallback"` is documented as historical — the engine can no longer produce it.
- Options (a) and (c) rejected: (a) violates ADR-0011's mandate, demonstrably masks
  bugs, spends judge tokens on an unmaterializable answer, and cannot run offline;
  (c) has no target class — the observed and plausible exceptions are deterministic
  (API drift / programming error), and genuinely transient faults already surface as
  `None` ratios or are retried at the transport layer.

## Consequences

- **A selection bug now halts a viability run with a traceback instead of limping to
  a plausible-looking report.** That is the point: the abort-action bug survived
  invisibly under policy (a); under (b) it would have failed the first run with
  `ValueError: Unsupported merge action`, pointing at the exact line.
- `fork_check` and any caller see the real exception; CI's fake-coordinator test flips
  from asserting the judge is consulted to asserting `abort_fork()` + re-raise + the
  logged warning (same-commit manifest flip on `crit-silent-judge-fallback`, per the
  Gate 2 protocol).
- Matrix E: failure paths produce the declared warning event and **no judge-model
  spans**; the E:errors row's "declared warning when the judge path fires" wording
  retires with the path.
- The bare-except anti-pattern is gone from the fork engine; the remaining `except`
  is narrow in scope (catch → log → abort → re-raise) and cannot change selection
  outcomes.
- Gate 6's live gated-fork session exercises the deterministic path only; if it ever
  trips the abort-raise, that is a real bug to fix, not noise to absorb — the exit
  gate treats it accordingly.

## Implementation sketch (lands only after this ADR is Accepted)

`forking.py`: replace the `except Exception:` body — keep `log.warning(...,
exc_info=True)` (reworded: "aborting fork" instead of "falling back to judge"), add
`await coordinator.abort_fork()` guarded best-effort, then `raise`. Delete the
`resolve`/`MergeStrategy` usage and import. Update
`test_selection_exception_falls_back_to_judge` →
`test_selection_exception_aborts_loud` (asserts: abort_fork called, no resolve call,
exception propagates, warning logged with traceback) and the fallback
`save_winner_dir` test accordingly. Flip `crit-silent-judge-fallback`'s note in
`parity/manifest.yml` in the same commit.
