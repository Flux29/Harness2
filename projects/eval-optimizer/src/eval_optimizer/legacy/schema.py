"""Typed data shapes for the Planner -> Tree-of-Generators -> Debate-Critics
pipeline. Stage flow: the Planner freezes an ExecutionPlan; Generators produce
Candidates; Critics score each Candidate along DIMENSIONS; the Rank step weights
those into RankedCandidates.

These are pure Pydantic models — no logic. The graph (graph.py) moves instances
of these through its nodes; the agents (agents.py, Workstream C) produce them.

ADR-0021: relocated here (Gen-1 legacy) from eval_optimizer.schema; the live
schema.py keeps only the Harness* models + Verdict.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# Critic dimensions, in scoring order. Weights used by the Rank step.
DIMENSIONS: tuple[str, ...] = ("correctness", "architecture", "performance")
DIMENSION_WEIGHTS: dict[str, float] = {
    "correctness": 0.5,
    "architecture": 0.2,
    "performance": 0.3,
}


class ExecutionPlan(BaseModel):
    """Planner output. Immutable for the rest of the pipeline — generators must
    not invent architecture mid-run."""

    model_config = {"frozen": True}

    goal: str
    steps: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    """One generated solution branch."""

    id: str
    approach: str            # e.g. "recursion flatten", "iterative stack"
    artifact: str            # the actual produced content (code, config, spec...)
    generator: str           # which generator produced it


class Critique(BaseModel):
    """One critic's judgement of one candidate along one dimension."""

    candidate_id: str
    dimension: str           # one of DIMENSIONS
    passed: bool
    score: int = Field(ge=0, le=10)
    findings: list[str] = Field(default_factory=list)


class RankedCandidate(BaseModel):
    """Aggregated weighted score for a candidate across all dimensions."""

    candidate_id: str
    total_score: float
    per_dimension: dict[str, int] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    """Terminal output of a graph run."""

    passed: bool
    iterations: int
    selected: Candidate | None = None
    plan: ExecutionPlan | None = None
    ranking: list[RankedCandidate] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


# --- Validation (C4/C5): the real, sandboxed pass/fail of a candidate -------

class CheckResult(BaseModel):
    """One check (syntax / lint / tests) run against a candidate's files."""

    name: str            # "parse" | "syntax" | "lint" | "tests"
    passed: bool
    detail: str = ""     # truncated stdout/stderr for diagnosis


class ValidationResult(BaseModel):
    """Outcome of running a candidate's generated code in the sandbox."""

    passed: bool                       # every check passed
    checks: list[CheckResult] = Field(default_factory=list)
    files_written: list[str] = Field(default_factory=list)
    tests_passed: int = 0
    tests_total: int = 0
    runner: str = "docker"             # which runner produced this


# --- Fork-based plan-viability (C5) -----------------------------------------

class BranchResult(BaseModel):
    """One forked branch: a candidate realized from the plan, then validated.

    `files` is the manifest of what the branch *would* have created — kept for
    the record; the actual files are deleted immediately after validation."""

    approach: str
    candidate_id: str
    files: list[str] = Field(default_factory=list)
    viable: bool = False               # passed syntax + lint + tests
    tests_passed: int = 0
    tests_total: int = 0
    validation: ValidationResult


class ForkReport(BaseModel):
    """Result of forking the frozen plan across approaches and validating each."""

    task: str
    plan: ExecutionPlan | None = None
    branches: list[BranchResult] = Field(default_factory=list)
    winner: str | None = None          # approach of the promoted viable branch
    any_viable: bool = False           # False => the plan itself is suspect
