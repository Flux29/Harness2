"""Workstream C2 check: verify the Generators produce diverse, plan-faithful
candidate implementations (in parallel).

Run: `uv run python -m eval_optimizer.generator_check`

Flow: Planner produces one ExecutionPlan, then 3 Generators implement it under
different approaches concurrently. Prints each candidate's size + a preview so you
can eyeball diversity and plan-faithfulness before we wire the full graph.
"""
from __future__ import annotations

import asyncio

from pydantic_ai_backends import StateBackend
from pydantic_deep import create_default_deps

from .agents import build_generator, build_planner
from .observability import setup_observability
from .runtime import agent_run, gather_limited
from .schema import Candidate

SAMPLE_TASK = (
    "Build a JSON field parity comparison tool: load two JSON files, flatten nested "
    "keys to dot-paths, compare field paths and types, and report missing, extra, and "
    "type-mismatched fields."
)
APPROACHES = ["recursive", "iterative-stack", "library-based (use stdlib only)"]


def _deps():
    return create_default_deps(StateBackend())


async def _run() -> int:
    planner = build_planner()
    generator = build_generator()

    plan = (await agent_run(planner, f"Produce an execution plan for:\n\n{SAMPLE_TASK}",
                            deps=_deps(), label="planner")).output
    print(f"plan goal: {plan.goal[:80]}...\n")

    plan_text = plan.model_dump_json(indent=2)

    def gen_factory(i: int, approach: str):
        async def _go() -> Candidate:
            prompt = (
                f"PLAN (immutable):\n{plan_text}\n\n"
                f"ASSIGNED APPROACH: {approach}\n\nImplement the full solution now."
            )
            out = (await agent_run(generator, prompt, deps=_deps(), label=f"gen:{approach[:12]}")).output
            return Candidate(id=f"cand-{i}", approach=approach, artifact=str(out), generator="glm")
        return _go

    # Parallel — OpenRouter handles concurrent requests fine (unlike NVIDIA's
    # burst-sensitive free tier). limit caps how many generators run at once.
    candidates = await gather_limited(
        [gen_factory(i, a) for i, a in enumerate(APPROACHES)], limit=3
    )

    for c in candidates:
        print(f"--- {c.id} | approach={c.approach} | {len(c.artifact)} chars ---")
        print("\n".join(c.artifact.splitlines()[:8]))
        print("...\n")

    ok = all(len(c.artifact) > 100 for c in candidates) and len({c.artifact for c in candidates}) == len(candidates)
    print("C2 PASSED: generators produced distinct, non-trivial candidates." if ok
          else "C2: candidates look thin or identical — inspect above.")
    return 0 if ok else 1


def main() -> int:
    setup_observability()
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
