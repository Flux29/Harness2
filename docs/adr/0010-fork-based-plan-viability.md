# ADR-0010 — Fork-based plan-viability (Live Forking) as C5

**Status:** Accepted · 2026-06-30 · Design in `docs/C5_FORK_PLAN.md`

## Context
The Debate-Critics (C3) judge candidates by reasoning, which can be wrong. Whether
a plan is *viable* is ultimately empirical: realize it, run its tests, see if it
works. pydantic-deep ships a checkpoint/fork capability ("Live forking"), and
pydantic-graph state is serializable — both let us branch from a shared
post-Plan checkpoint and explore realizations cheaply, with rewind-on-failure.
This is a deliberate **scope expansion** beyond the original narrow milestone
(see PDR §0); it's justified because end-to-end plan-viability is the core signal
the build exists to produce, and it completes C4's Validate step rather than
adding an orthogonal feature.

## Decision
Adopt **C5 — fork-based plan-viability**: after the frozen `ExecutionPlan`,
fork one branch per candidate approach, run each branch `Generate → Validate` to
a **real sandboxed pass/fail**, compare actual outcomes (tests passed, lint,
runtime — not critic scores), and promote a viable winner (or flag the plan as
non-viable if none pass).

**Forking axis:** graph-level (serializable `PipelineState`) is the deterministic
**spine**; harness-level checkpoints (`fork_from_checkpoint`) are an optional
interactive layer added later. Rationale follows ADR-0008/0006: reproducibility
and auditability are the product for an evaluation engine.

**Validate** runs in the Docker sandbox (`pydantic-ai-backend` / harness
`sandbox=True`): syntax → ruff → pytest → exit code. This is shared with C4.

## Consequences
- Plan viability becomes an executed verdict, not an opinion — much stronger
  signal for the agent-bootstrapping process.
- Requires the Docker sandbox wired for code execution (new `validate.py`); higher
  per-task cost (N branches each generate + run) — bounded by `gather_limited`
  concurrency and beam width.
- New modules: `validate.py`, `forking.py`, `fork_check.py`; new schema types
  `ValidationResult`, `ForkReport`. Each fork is a Logfire span (ADR-0009) for
  live observability.
- Scope guardrail: the POC is graph-level only; harness interactive forking,
  beam depth > 1, and `ForkReport` persistence stay parked until the spine works.
