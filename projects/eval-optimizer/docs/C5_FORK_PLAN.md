# C5 — Fork-based Plan-Viability (Live Forking POC)

**Status:** Design · 2026-06-30 · Builds on the verified C1–C2 agents, the
pydantic-graph control plane (ADR-0006), and the kept custom surface (ADR-0008).

## The idea in one sentence
Don't just *score* a plan's candidates statically (the Debate-Critics) — **fork
at the frozen plan and run each candidate all the way to a real, sandboxed
pass/fail**, so "is this plan actually viable?" is answered by execution, not
opinion.

## Why this is worth the scope
The critics (C3) judge candidates by reasoning; that can be wrong. Plan viability
is ultimately an *empirical* question: realize the plan, run its tests, see if it
works. Forking from a shared post-Plan checkpoint makes exploring N realizations
cheap (shared prefix) and gives rewind-on-failure for free. This is the
end-to-end "does the plan hold up?" signal Steven asked for.

## Two forking axes (and which we use)
- **Harness-level** — pydantic-deep checkpoints: `include_checkpoints=True`,
  `checkpoint_frequency`, `CheckpointStore` (in-memory/file),
  `fork_from_checkpoint(store, checkpoint_id=...)`, `RewindRequested`. Operates on
  *agent conversation/message history*. Great for interactive/CLI exploration.
- **Graph-level** — pydantic-graph's serializable `PipelineState`: snapshot after
  Plan, restore N branches, run each independently. Deterministic, reproducible,
  already persists to Postgres + shows in Logfire.

**Decision:** graph-level forking is the **spine** of the POC (determinism +
reproducibility are the product for an evaluation engine); harness checkpoints
are an optional interactive layer for ad-hoc "fork this session and try X". See
ADR-0010.

## Flow
```
 task ─▶ Plan (once, frozen) ─▶ [base checkpoint]
                                   │  fork per approach
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                      ▼
        branch A (recursive)  branch B (iterative)  branch C (library)
        Generate→Validate*    Generate→Validate*    Generate→Validate*
              │                    │                      │
              └────────────────────┼──────────────────────┘
                                   ▼
                       Compare REAL outcomes  ─▶  promote viable winner
                       (tests passed? lint?      (or: no branch viable
                        runtime ok?)              → plan is suspect → re-plan)
```
`Validate*` is the **real** sandboxed check (this also completes C4's Validate):
parse files out of the generator output → write to a temp workspace → run in the
Docker sandbox (`pydantic-ai-backend` / harness `sandbox=True`):
**syntax → ruff (static) → pytest (unit) → exit code**. The branch's verdict is
its actual test result, not a critic's guess.

## New pieces (POC, deliberately small)
- `src/eval_optimizer/validate.py` — `validate_artifact(files) -> ValidationResult`
  (syntax/lint/test in the Docker sandbox). Shared by C4 and C5.
- `src/eval_optimizer/forking.py` — `run_forked_viability(task, approaches) ->
  ForkReport`: Plan once, snapshot, fork per approach, run Generate+Validate per
  branch (bounded concurrency via `gather_limited`), collect per-branch results.
- `src/eval_optimizer/schema.py` — add `ValidationResult` and `ForkReport`
  (per-branch: approach, files, tests_passed/total, lint_ok, runtime_ok, viable).
- `fork_check.py` — runnable POC: prints each branch's real outcome and the
  promoted winner; every fork wrapped in a Logfire span.

## Exit criterion
Given a task, the harness: produces one frozen plan, forks ≥3 approach branches,
runs each to a **sandboxed** verdict, and reports which approaches are *viable*
(generated code passes tests) — promoting a viable winner, or flagging the plan
as non-viable if none pass. Observable live in Logfire (one span per branch).

## Parking-lot (not in the POC)
- Harness-level `fork_from_checkpoint` interactive mode (add after the graph
  spine works).
- Sub-variant trees (beam depth > 1) per Schema.txt §3.
- Persisting `ForkReport` to `agent_state` for the outer harness-optimization loop.
