"""The two agents: Optimizer (generator) and Evaluator (skeptic).

NOTE: the exact ``create_deep_agent`` keyword set should be verified against the
installed pydantic-deep version (`uv run python -c "import pydantic_deep, inspect;
print(inspect.signature(pydantic_deep.create_deep_agent))"`). The kwargs used here
are from the documented public API.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .models import build_glm_model, build_model
from .schema import ExecutionPlan


class Verdict(BaseModel):
    """Structured judgement returned by the Evaluator. Type-safe, no JSON parsing."""

    passed: bool = Field(description="True only if EVERY acceptance criterion is met.")
    score: int = Field(ge=0, le=100, description="Overall score against the spec.")
    issues: list[str] = Field(
        default_factory=list,
        description="Each entry names the spec criterion it violates and why.",
    )
    suggested_fixes: list[str] = Field(
        default_factory=list,
        description="Concrete, actionable fixes the Optimizer can apply next iteration.",
    )


OPTIMIZER_INSTRUCTIONS = (
    "You are the OPTIMIZER. Given a goal and an acceptance spec, produce the best "
    "artifact you can that satisfies every criterion in the spec. If you are given "
    "evaluator feedback from a previous attempt, address each point directly. "
    "Produce the artifact itself as your final answer. Do NOT grade your own work."
)

EVALUATOR_INSTRUCTIONS = (
    "You are the EVALUATOR, and you are skeptical by default. Judge the artifact "
    "ONLY against the provided acceptance spec — not against your own taste. For "
    "each criterion, decide pass/fail and cite the specific reason. Set passed=True "
    "only if every criterion is met. Be concrete in issues and suggested_fixes so "
    "the optimizer can act on them. Do NOT edit or rewrite the artifact yourself."
)


PLANNER_INSTRUCTIONS = (
    "You are the PLANNER. Given a coding/build task, produce a structured "
    "ExecutionPlan: a clear goal, an ordered list of concrete steps, the modules "
    "(files) to create, and the key functions. Think carefully and thoroughly. "
    "The plan must be complete and unambiguous because downstream generators "
    "build strictly from it and must NOT invent architecture. Do NOT write the "
    "implementation code yourself — only the plan."
)


def build_planner(model: Any | None = None) -> Any:
    """High-reasoning Planner (deep-agent harness) -> structured ExecutionPlan.

    Model defaults to PLANNER_MODEL (e.g. openrouter:z-ai/glm-5.1 or z-ai/glm-5.1).
    """
    from pydantic_deep import create_deep_agent
    from .config import Settings

    return create_deep_agent(
        model=model or build_model(Settings.from_env().planner_model),
        output_type=ExecutionPlan,
        thinking="high",
        instructions=PLANNER_INSTRUCTIONS,
    )


GENERATOR_INSTRUCTIONS = (
    "You are a GENERATOR. Implement the task STRICTLY following the provided "
    "ExecutionPlan and your assigned APPROACH. Produce complete, runnable Python. "
    "Concatenate all modules in one response, each preceded by a "
    "'# === <filename> ===' marker matching the plan's modules. Do NOT invent "
    "architecture beyond the plan. Output only code with minimal docstrings."
)


def build_generator(model: Any | None = None) -> Any:
    """Generator (deep-agent harness): implements the plan under one approach.

    Defaults to GENERATOR_MODEL.
    """
    from pydantic_deep import create_deep_agent
    from .config import Settings

    return create_deep_agent(
        model=model or build_model(Settings.from_env().generator_model),
        thinking="medium",
        instructions=GENERATOR_INSTRUCTIONS,
    )


def build_optimizer(model: Any | None = None) -> Any:
    from pydantic_deep import create_deep_agent

    return create_deep_agent(
        model=model or build_glm_model(),
        include_memory=True,
        include_todo=True,
        context_manager=True,
        cost_tracking=True,
        instructions=OPTIMIZER_INSTRUCTIONS,
    )


def build_evaluator(model: Any | None = None) -> Any:
    """Skeptical Evaluator/Critic (deep-agent harness) -> structured Verdict.

    Defaults to CRITIC_MODEL.
    """
    from pydantic_deep import create_deep_agent
    from .config import Settings

    return create_deep_agent(
        model=model or build_model(Settings.from_env().critic_model),
        output_type=Verdict,
        include_memory=True,
        cost_tracking=True,
        instructions=EVALUATOR_INSTRUCTIONS,
    )
