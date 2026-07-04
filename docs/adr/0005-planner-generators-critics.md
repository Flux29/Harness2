# ADR-0005 — Planner → Tree-of-Generators → Debate-Critics architecture

**Status:** Accepted · 2026-06-29 (evolves the 2-agent evaluator-optimizer in PDR §3)

## Context
The initial deliverable was a two-agent evaluator-optimizer loop (Optimizer +
Evaluator). It proved the loop mechanics, but a single generation trajectory is
the biggest weakness of LLM coding agents. `E:\Schema\Schema.txt` specifies a
stronger pattern: explore a tree of candidate solutions, then have multiple
critics debate and rank them.

## Decision
Adopt the **Planner → Tree-of-Generators → Debate-Critics** architecture:
- **Planner** (high reasoning) emits an **immutable** `ExecutionPlan`
  (goal, steps, modules, functions). Generators may not invent architecture.
- **Tree of Generators** (low/med) produces N diverse candidates (beam width 3),
  varying approach/algorithm/structure.
- **Debate Critics** (high) — **Correctness / Architecture / Performance** — each
  returns a structured `Critique`; a weighted `Rank` (0.5 / 0.2 / 0.3) selects the
  top candidate.
- **Validate** runs syntax → static analysis → tests → runtime in the Docker
  sandbox; failure triggers *targeted regeneration*, not a restart.

Reasoning budget: Planner high, Generators low–med, Critics high. Types live in
`schema.py`; the two-agent `loop.py` is retained as a legacy reference path.

## Consequences
- Reduces single-trajectory collapse; critics act as automated multi-reviewers.
- Higher token/latency cost per task (multiple generators × multiple critics) —
  mitigated by bounded beam width, capped critics, and per-role model choice
  (ADR-0003).
- More moving parts; the graph (ADR-0006) keeps them ordered and resumable.
