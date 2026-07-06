"""Typed data shapes for the LIVE path (ADR-0021 trimmed).

Only the harness-native Live-Fork models (ADR-0011/0017/0018) and the reusable
`Verdict` (extracted from the retired agents.py) live here. The Gen-1 pipeline
models moved to eval_optimizer.legacy.schema.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


# --- Harness-native Live Forking (C5, ADR-0011) -----------------------------

class HarnessBranchResult(BaseModel):
    """One branch from pydantic-deep Live Run Forking, with its real test outcome."""

    branch_id: str
    label: str
    test_pass_ratio: float | None = None   # SHARED suite outcome (ADR-0018); binary in
                                           # practice (1.0/0.0/None); None = no signal
    cost_usd: float | None = None
    turns: int = 0
    error_count: int = 0
    preview: str = ""                      # truncated final assistant message
    # ADR-0018, ADDITIVE: True when the branch's overlay touched the shared
    # suite or pytest config — the branch is disqualified from selection.
    tests_tampered: bool = False


class HarnessForkReport(BaseModel):
    """Outcome of a harness Live-Fork viability run."""

    task: str
    branches: list[HarnessBranchResult] = Field(default_factory=list)
    winner_branch_id: str | None = None
    any_viable: bool = False               # a branch's tests passed and it was merged
    winner_dir: str | None = None          # where the winning tree was materialized (if saved)
    # Phase 4.5 (crit-silent-judge-fallback), ADDITIVE: which selection path
    # produced the winner. None = no winner (abort). "judge_fallback" is
    # HISTORICAL: ADR-0017 retired that path (selection failures now abort
    # loud and re-raise); the literal stays for schema stability.
    selection_path: Literal["deterministic", "judge_fallback"] | None = None
