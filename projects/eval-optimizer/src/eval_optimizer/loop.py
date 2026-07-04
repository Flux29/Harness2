"""The bounded evaluator-optimizer loop.

Optimizer produces -> Evaluator judges -> on fail, structured feedback feeds the
next Optimizer iteration -> repeat until pass or max_iterations. Bounded so a bad
spec can't loop forever (and to respect the NVIDIA free-tier rate limit).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .agents import Verdict, build_evaluator, build_optimizer


@dataclass
class Iteration:
    n: int
    artifact: str
    verdict: Verdict


@dataclass
class LoopResult:
    passed: bool
    iterations: int
    final_artifact: str
    final_verdict: Verdict | None
    history: list[Iteration] = field(default_factory=list)


def _fresh_deps() -> Any:
    """Create isolated harness deps for one agent run."""
    from pydantic_ai_backends import StateBackend
    from pydantic_deep import create_default_deps

    return create_default_deps(StateBackend())


def _optimizer_prompt(goal: str, spec: str, feedback: str) -> str:
    base = f"GOAL:\n{goal}\n\nACCEPTANCE SPEC:\n{spec}\n"
    if feedback:
        base += (
            "\nThe previous attempt FAILED evaluation. Address every point below, "
            f"then produce a corrected artifact:\n{feedback}\n"
        )
    base += "\nProduce the artifact now as your final answer."
    return base


def _evaluator_prompt(spec: str, artifact: str) -> str:
    return (
        f"ACCEPTANCE SPEC:\n{spec}\n\n"
        f"ARTIFACT TO JUDGE:\n{artifact}\n\n"
        "Return your structured verdict."
    )


def _format_feedback(verdict: Verdict) -> str:
    lines = [f"- issue: {i}" for i in verdict.issues]
    lines += [f"- fix: {f}" for f in verdict.suggested_fixes]
    return "\n".join(lines) if lines else "(no specifics given)"


async def run_loop(
    goal: str,
    spec: str,
    *,
    max_iterations: int = 4,
    optimizer: Any | None = None,
    evaluator: Any | None = None,
    persist_agent: str | None = None,
    project: str = "eval-optimizer",
) -> LoopResult:
    """Run the bounded evaluator-optimizer loop.

    If ``persist_agent`` is set (e.g. "optimizer"), progress/verdict/failure rows
    are written to memory_common.agent_state and the latest prior progress is read
    at start (resume-on-restart). Leave it None for a pure in-memory run.
    """
    optimizer = optimizer or build_optimizer()
    evaluator = evaluator or build_evaluator()

    mem = None
    if persist_agent:
        from .memory_pg import Memory  # lazy: only needs Postgres when persisting

        mem = Memory()
        prior = mem.latest_state("progress", persist_agent)
        if prior:
            print(f"[resume] last progress @ {prior['updated_at']}: {prior['data']}")

    feedback = ""
    artifact = ""
    verdict: Verdict | None = None
    history: list[Iteration] = []

    for n in range(1, max_iterations + 1):
        opt_result = await optimizer.run(_optimizer_prompt(goal, spec, feedback), deps=_fresh_deps())
        artifact = str(opt_result.output)

        eval_result = await evaluator.run(_evaluator_prompt(spec, artifact), deps=_fresh_deps())
        verdict = eval_result.output  # typed Verdict

        history.append(Iteration(n=n, artifact=artifact, verdict=verdict))
        print(f"[iter {n}] passed={verdict.passed} score={verdict.score} issues={len(verdict.issues)}")

        if mem:
            progress = {
                "project": project,
                "goal": goal,
                "iteration": n,
                "passed": verdict.passed,
                "score": verdict.score,
                "issues": verdict.issues,
            }
            mem.save_state(f"{project}:progress", persist_agent, "progress", progress)

        if verdict.passed:
            if mem:
                mem.save_state(
                    f"{project}:verdict",
                    persist_agent,
                    "verdict",
                    {"score": verdict.score, "artifact": artifact},
                )
            break

        feedback = _format_feedback(verdict)
    else:
        if mem and verdict:
            mem.save_state(
                f"{project}:failure",
                persist_agent,
                "failure_log",
                {"goal": goal, "iterations": len(history), "last_issues": verdict.issues},
            )

    return LoopResult(
        passed=bool(verdict and verdict.passed),
        iterations=len(history),
        final_artifact=artifact,
        final_verdict=verdict,
        history=history,
    )


if __name__ == "__main__":
    # Phase 2 smoke: a tiny throwaway task with a crisp, mechanically-checkable spec.
    demo_goal = "Write a Python function `is_palindrome(s: str) -> bool`."
    demo_spec = (
        "1. Signature is exactly `def is_palindrome(s: str) -> bool`.\n"
        "2. Case-insensitive and ignores non-alphanumeric characters.\n"
        "3. Includes at least 3 doctest examples that pass.\n"
        "4. No imports beyond the standard library."
    )
    result = asyncio.run(run_loop(demo_goal, demo_spec, max_iterations=4))
    print(f"\nPASSED={result.passed} after {result.iterations} iteration(s)")
    print("--- final artifact ---")
    print(result.final_artifact)
