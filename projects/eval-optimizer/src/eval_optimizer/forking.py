"""C5 — harness-native Live Run Forking (ADR-0011).

Replaces the hand-rolled fork/validate/rank loop with pydantic-deep's built-in
Live Run Forking:
  1. one builder agent produces a short plan (the shared prefix),
  2. we fork one branch per approach; each branch implements the task, writing
     files to its own copy-on-write overlay,
  3. the harness runs each branch's pytest suite (`test_command`),
  4. we pick the branch with the best test-pass ratio (deterministic) and merge it;
     losers are discarded automatically. Per-branch + aggregate budgets cap cost.

Trade-offs (ADR-0011): tests run on the host via `LocalBackend` (not our Docker
sandbox); selection is by test-pass ratio, not the LLM judge (with a judge fallback).

RUNTIME-VERIFY: the fork→wait→select sequence and the per-branch outcome read
(`branch_outcomes`, the public vendor-patch accessor) run here; if the API differs, the
`resolve(auto)` fallback still selects a winner.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile

from pydantic_deep import (
    BranchIsolation,
    BranchSpec,
    DeepAgentDeps,
    InMemoryCheckpointStore,
    LiveForkCapability,
    LocalBackend,
    MergeStrategy,
    create_deep_agent,
)

from .config import Settings
from .models import build_model
from .observability import setup_observability
from .schema import HarnessBranchResult, HarnessForkReport

# (label, steer) per branch
DEFAULT_APPROACHES: list[tuple[str, str]] = [
    ("recursive", "Implement using a clear, straightforward (recursive where natural) approach."),
    ("iterative", "Implement using an explicit iterative approach, avoiding recursion."),
    ("stdlib-min", "Implement using only the Python standard library — minimal and dependency-free."),
]

BUILDER_INSTRUCTIONS = (
    "You implement small Python tasks. Using your file tools, write all source files "
    "AND a pytest test suite into the working directory. Keep it minimal and correct. "
    "When everything is written, STOP — do not start long-running or background processes."
)

_RUNNING_STATES = {"running", "pending", "starting"}


def _builder_agent():
    s = Settings.from_env()
    return create_deep_agent(
        model=build_model(s.generator_model),
        forking=LiveForkCapability(
            test_command="pytest -q",
            test_timeout_s=90.0,
            max_branches=8,
            keep_artifacts=False,   # discard branch overlays; winner flushes to parent
        ),
        include_checkpoints=True,
        thinking="low",             # keep branches cheap and fast
        instructions=BUILDER_INSTRUCTIONS,
    )


async def _wait_for_branches(coordinator, poll_s: float = 2.0, timeout_s: float = 900.0):
    waited = 0.0
    while waited < timeout_s:
        statuses = coordinator.inspect_branches()
        if not any(str(s.state).lower() in _RUNNING_STATES for s in statuses):
            return statuses
        await asyncio.sleep(poll_s)
        waited += poll_s
    return coordinator.inspect_branches()


async def run_forked_viability(
    task: str,
    approaches: list[tuple[str, str]] | None = None,
    *,
    save_winner_dir: str | None = None,
    per_branch_budget_usd: float = 0.75,
    aggregate_budget_usd: float = 2.5,
) -> HarnessForkReport:
    setup_observability()
    approaches = approaches or DEFAULT_APPROACHES

    work = tempfile.mkdtemp(prefix="evalopt-fork-")
    agent = _builder_agent()
    deps = DeepAgentDeps(
        backend=LocalBackend(root_dir=work, enable_execute=True),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    coordinator = None
    try:
        # Parent run: produce a short plan; this also initializes the fork coordinator.
        parent = await agent.run(
            f"Produce a short implementation plan for this task, then stop:\n\n{task}",
            deps=deps,
        )
        coordinator = deps.fork_coordinator
        if coordinator is None:
            raise RuntimeError("fork_coordinator not set — is forking enabled on the agent?")

        specs = [
            BranchSpec(label=label, steer=f"{steer}\n\nTask:\n{task}",
                       budget_usd=per_branch_budget_usd)
            for label, steer in approaches
        ]
        await coordinator.fork(
            specs,
            parent_history=list(parent.all_messages()),
            isolation=BranchIsolation(),
            aggregate_budget_usd=aggregate_budget_usd,
        )
        await _wait_for_branches(coordinator)

        # Deterministic selection by test-pass ratio; judge fallback if the API differs.
        branches: list[HarnessBranchResult] = []
        winner_id: str | None = None
        try:
            outcomes = await coordinator.branch_outcomes()  # public vendor-patch API (ADR-0011)
            for o in outcomes:
                branches.append(HarnessBranchResult(
                    branch_id=o.branch_id, label=o.branch_label,
                    test_pass_ratio=o.test_pass_ratio, cost_usd=o.cost_usd,
                    turns=o.turns, error_count=o.error_count,
                    preview=(o.final_assistant_message or "")[:200],
                ))
            ranked = sorted(
                branches,
                key=lambda b: b.test_pass_ratio if b.test_pass_ratio is not None else -1.0,
                reverse=True,
            )
            best = ranked[0] if ranked else None
            if best and best.test_pass_ratio and best.test_pass_ratio > 0:
                merge = await coordinator.merge_or_select(f"pick:{best.branch_id}")
                winner_id = merge.winner_branch_id
            else:
                await coordinator.merge_or_select("abort")
        except Exception:
            outcome = await coordinator.resolve(strategy=MergeStrategy(kind="auto"))
            if outcome.merge_result is not None:
                winner_id = outcome.merge_result.winner_branch_id

        any_viable = winner_id is not None
        winner_dir = None
        if any_viable and save_winner_dir:
            shutil.copytree(work, save_winner_dir, dirs_exist_ok=True)
            winner_dir = save_winner_dir

        return HarnessForkReport(
            task=task, branches=branches, winner_branch_id=winner_id,
            any_viable=any_viable, winner_dir=winner_dir,
        )
    finally:
        if coordinator is not None:
            try:
                await coordinator.aclose()
            except Exception:
                pass
        shutil.rmtree(work, ignore_errors=True)   # discard the working tree; winner already captured
