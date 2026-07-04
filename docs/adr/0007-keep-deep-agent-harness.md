# ADR-0007 — Keep the deep-agent harness (bare-Agent refactor rejected)

**Status:** Accepted · 2026-06-29

## Context
While debugging structured-output failures on the local `qwen2.5-coder:7b`, the
model wandered into calling harness tools (e.g. `start_monitor`) instead of
emitting the `ExecutionPlan`. One proposed fix was to drop `create_deep_agent`
for the Planner/Generator/Critic roles and use bare `pydantic_ai.Agent`s with no
tools, so a weak model physically cannot wander.

## Decision
**Reject the bare-Agent refactor; keep all roles on the deep-agent harness**
(`create_deep_agent`). The tool-wandering was a *model-capability* problem, not a
harness problem — it disappears with a capable model (GLM-via-OpenRouter,
Sonnet/Opus). Removing the harness would introduce confounding variables and lose
its memory/hooks/cost-tracking, which we want for the real agents. Owner decision:
avoid confounders and protect the harness wiring.

## Consequences
- Consistent architecture; harness capabilities available to every role.
- The fix for structured-output reliability is **model choice** (ADR-0003), not
  stripping the harness.
- The check scripts pass harness `deps` (`create_default_deps(StateBackend())`);
  structured output uses the harness default (tool mode), which works on capable
  tool-calling models.
- A brief experiment with bare Agents + `PromptedOutput` was made and fully
  reverted; recorded here so the path isn't re-tried without new evidence.
