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
sandbox); selection is by test-pass ratio, not the LLM judge. Selection failures
abort the fork and re-raise (ADR-0017) — the v1 judge fallback is retired from
this programmatic path.

Phase 5.2 (crit-fork-exec-gate): host execution of LLM-generated code is an
EXPLICIT CONFIGURATION, not a docstring disclosure — `run_forked_viability`
refuses to run unless ``EVALOPT_ALLOW_HOST_EXEC=1`` is set. Set it only on a
machine you trust with generated code (fork_check's "machine you trust" note,
promoted to a required acknowledgment).

RUNTIME-VERIFY: the fork→wait→select sequence and the per-branch outcome read
(`branch_outcomes`, the public vendor-patch accessor) run here; if the API drifts,
the run fails loud with the real exception (ADR-0017) instead of limping to a
judge answer — that silence is how disc-abort-action-unsupported hid.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Literal

from pydantic_deep import (
    BranchIsolation,
    BranchSpec,
    DeepAgentDeps,
    InMemoryCheckpointStore,
    LiveForkCapability,
    LocalBackend,
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

log = logging.getLogger("eval_optimizer.forking")


def _builder_agent():
    s = Settings.from_env()
    return create_deep_agent(
        model=build_model(s.generator_model),
        forking=LiveForkCapability(
            test_command=s.fork_test_command,
            test_timeout_s=s.fork_test_timeout_s,
            max_branches=s.fork_max_branches,
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
    # Timeout (Phase 4.6, crit-no-branch-cancel): explicitly terminate the
    # outstanding branches BEFORE selection. v1 returned here with branches
    # still live, racing the merge against still-writing tasks.
    for s in coordinator.inspect_branches():
        if str(s.state).lower() in _RUNNING_STATES:
            try:
                await coordinator.terminate_branch(s.id, reason="timeout")
            except Exception:
                log.warning("failed to terminate branch %s after timeout",
                            s.id, exc_info=True)
    return coordinator.inspect_branches()


async def run_forked_viability(
    task: str,
    approaches: list[tuple[str, str]] | None = None,
    *,
    save_winner_dir: str | None = None,
    per_branch_budget_usd: float | None = None,
    aggregate_budget_usd: float | None = None,
) -> HarnessForkReport:
    # Phase 5.2 (crit-fork-exec-gate): required env acknowledgment — branches
    # write LLM-generated code and run its pytest suite ON THIS HOST.
    if os.environ.get("EVALOPT_ALLOW_HOST_EXEC", "").strip() != "1":
        raise RuntimeError(
            "EVALOPT_ALLOW_HOST_EXEC=1 is required: fork branches execute "
            "LLM-generated code and its test suite on this host (LocalBackend, "
            "ADR-0011 trade-off). Set it only on a machine you trust with "
            "generated code."
        )
    setup_observability()
    # Fork budgets come from the single declared config (Phase 3.5); explicit
    # args still override. Defaults are unchanged (0.75 / 2.5).
    _s = Settings.from_env()
    if per_branch_budget_usd is None:
        per_branch_budget_usd = _s.fork_per_branch_budget_usd
    if aggregate_budget_usd is None:
        aggregate_budget_usd = _s.fork_aggregate_budget_usd
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

        # Deterministic selection by test-pass ratio (ADR-0011); failures
        # abort loud (ADR-0017), never fall back to the judge.
        branches: list[HarnessBranchResult] = []
        winner_id: str | None = None
        selection_path: Literal["deterministic", "judge_fallback"] | None = None
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
                if winner_id is not None:
                    selection_path = "deterministic"
            else:
                # Discovered in Phase 4 (disc-abort-action-unsupported): v1
                # called merge_or_select("abort"), an action the vendor API
                # never supported — the ValueError fell into the bare except
                # below and the JUDGE quietly merged a winner on a path whose
                # stated intent was "no branch passed, abort". abort_fork()
                # is the real abort API: discard all branches, merge nothing.
                await coordinator.abort_fork()
        except Exception:
            # ADR-0017 (6.2): a selection failure is an infrastructure or
            # programming error, never evidence about the plan. Log it, abort
            # the fork (cancel branches, merge nothing), re-raise. The v1
            # judge fallback here silently violated ADR-0011's deterministic
            # mandate and masked exactly this bug class
            # (disc-abort-action-unsupported).
            log.warning(
                "deterministic fork selection failed; aborting fork (ADR-0017)",
                exc_info=True,
            )
            try:
                await coordinator.abort_fork()
            except Exception:
                log.warning("abort_fork after selection failure also failed",
                            exc_info=True)
            raise

        any_viable = winner_id is not None
        winner_dir = None
        # Phase 4.6 (crit-no-branch-cancel): copy ONLY when the deterministic
        # merge path actually flushed the winner into the work tree. v1 also
        # copied on the judge-fallback path, materializing a "winner dir" that
        # was never proven to contain the winner's files; abort never copies.
        if selection_path == "deterministic" and save_winner_dir:
            shutil.copytree(work, save_winner_dir, dirs_exist_ok=True)
            winner_dir = save_winner_dir

        return HarnessForkReport(
            task=task, branches=branches, winner_branch_id=winner_id,
            any_viable=any_viable, winner_dir=winner_dir,
            selection_path=selection_path,
        )
    finally:
        if coordinator is not None:
            try:
                await coordinator.aclose()
            except Exception:
                pass
        shutil.rmtree(work, ignore_errors=True)   # discard the working tree; winner already captured
