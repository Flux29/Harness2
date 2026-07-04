# ADR-0002 — pydantic-deepagents as the agent harness

**Status:** Accepted · 2026-06-29

## Context
The DevDrive plan proposed hand-building an agent harness: lifecycle hooks,
subagents, persistent memory, context compression, cost tracking, a
Planner/Generator/Evaluator structure. That is a large amount of framework code
to own and maintain.

## Decision
Adopt **`pydantic-deepagents`** (PyPI `pydantic-deep`, built on `pydantic-ai`) as
the harness. It already ships tool-calling, per-agent memory, subagents/swarm,
Claude-Code-style `PRE/POST_TOOL_USE` hooks, structured output, context
auto-summarization, stuck-loop detection, and cost tracking, and works with any
OpenAI-compatible provider. Our job is configuration + orchestration, not
framework construction.

## Consequences
- Massive reduction in bespoke code; inherit battle-tested capabilities.
- Coupled to pydantic-ai's release cadence (it moved to 2.x mid-build; see
  ADR-0006).
- The full harness gives weak models many tools to misuse — relevant when
  choosing models and agent shapes (ADR-0003, ADR-0007).
- We depend on `pydantic-ai` ≥ 2.0 (pinned transitively by pydantic-deep).
