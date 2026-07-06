"""Workstream C1 check: verify the Planner agent (GLM 5.1 by default) produces a
sound, structured ExecutionPlan.

Run: `uv run python -m eval_optimizer.planner_check`

This isolates the highest-reasoning step. If the plan looks good on GLM, we wire
all the real agents into the graph. To try Claude Sonnet instead, set
PLANNER_MODEL=anthropic:claude-sonnet-4-6 (+ ANTHROPIC_API_KEY) and re-run.
"""
from __future__ import annotations

import asyncio

from pydantic_ai_backends import StateBackend
from pydantic_deep import create_default_deps

from .agents import build_planner
from ..config import Settings
from ..observability import setup_observability
from .runtime import agent_run


SAMPLE_TASK = (
    "Build a JSON field parity comparison tool: load two JSON files, normalize and "
    "flatten nested keys, compare field paths between the two, and produce a "
    "discrepancy report listing missing, extra, and type-mismatched fields."
)


def main() -> int:
    setup_observability()
    print(f"Planner model: {Settings.from_env().planner_model}\n")
    planner = build_planner()
    deps = create_default_deps(StateBackend())

    result = asyncio.run(
        agent_run(planner, f"Produce an execution plan for this task:\n\n{SAMPLE_TASK}",
                  deps=deps, label="planner")
    )
    plan = result.output  # typed ExecutionPlan

    print("=== ExecutionPlan ===")
    print("goal     :", plan.goal)
    print("steps    :")
    for i, s in enumerate(plan.steps, 1):
        print(f"   {i}. {s}")
    print("modules  :", plan.modules)
    print("functions:", plan.functions)

    ok = bool(plan.goal and plan.steps and plan.modules)
    print("\nC1 PASSED: GLM produced a structured plan." if ok
          else "\nC1: plan looks thin — inspect above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
