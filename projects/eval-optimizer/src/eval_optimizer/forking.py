"""C5 — harness-native Live Run Forking (ADR-0011).

Replaces the hand-rolled fork/validate/rank loop with pydantic-deep's built-in
Live Run Forking, selecting on a SHARED suite (ADR-0018):
  1. the shared test suite enters the work tree exactly once — caller-supplied
     (`tests=`) or authored by the parent builder run (the shared prefix),
  2. we fork one branch per approach; each branch implements the task against
     that suite, writing to its own copy-on-write overlay,
  3. the harness runs the suite per branch (`test_command`, binary pass/fail),
  4. branches whose overlays touched tests/ (or pytest config) are DISQUALIFIED
     (integrity check over the public diff API — sees deletions too); among
     untampered full passes we pick by fewest errors, then lowest cost, then
     approach order, and merge; losers are discarded automatically. No judge.
     Per-branch + aggregate budgets cap cost.

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

from pathlib import Path

from pydantic_deep import (
    BranchIsolation,
    BranchSpec,
    DeepAgentDeps,
    InMemoryCheckpointStore,
    LiveForkCapability,
    LocalBackend,
    build_diff_report,
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

# ADR-0018: branches implement; they do NOT grade. The shared suite is authored
# once (caller-supplied or by the parent run) and enters every branch via the
# copy-on-write prefix; the write-your-own-tests clause is gone.
BUILDER_INSTRUCTIONS = (
    "You work on small Python tasks using your file tools in the working "
    "directory. Keep it minimal and correct. When everything you were asked to "
    "write is written, STOP — do not start long-running or background processes."
)

_SUITE_AUTHOR_PROMPT = (
    "Using your file tools, write ONLY a pytest test suite for this task into "
    "the tests/ directory (files named test_*.py). The suite is the acceptance "
    "contract every implementation attempt must satisfy — make it test the "
    "task's actual requirements. Do NOT implement the solution itself. When "
    "the suite is written, stop.\n\nTask:\n{task}"
)

_PLAN_PROMPT = "Produce a short implementation plan for this task, then stop:\n\n{task}"

_STEER_CONTRACT = (
    "\n\nImplement the task so the EXISTING shared test suite under tests/ "
    "passes. Do NOT create, modify, or delete anything under tests/ or any "
    "pytest configuration file — branches that touch the suite are "
    "disqualified (ADR-0018)."
)

# Paths a branch may not touch (ADR-0018 integrity check): the shared suite,
# plus root-level pytest configuration that could reroute or mute it.
_PROTECTED_ROOT_FILES = {"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"}

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


def _is_protected_test_path(path: str) -> bool:
    p = path.replace("\\", "/").lstrip("/")
    return p.startswith("tests/") or p in _PROTECTED_ROOT_FILES


async def _tampered_branch_ids(coordinator, fork_id: str) -> set[str]:
    """ADR-0018 integrity check: a branch whose end-state touches the shared
    suite (or root pytest config) is disqualified. Read from the LIVE overlays
    via the vendor's public diff API — end-state classification includes
    deletions, which the on-disk artifact mirror cannot see. Must run BEFORE
    merge/abort (those release the overlays)."""
    report = await build_diff_report(fork_id, list(coordinator.branches.values()))
    tampered: set[str] = set()
    for path_diff in report.paths:
        if not _is_protected_test_path(path_diff.path):
            continue
        for branch_id, change in path_diff.branches.items():
            if change.operation != "untouched":
                tampered.add(branch_id)
    return tampered


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
    tests: dict[str, str] | None = None,
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
        # ADR-0018: the shared suite enters the fork EXACTLY ONCE, via the
        # shared prefix — caller-supplied when available, else authored by the
        # parent run below. Branches inherit it read-only (integrity-checked).
        if tests is not None:
            for rel, content in tests.items():
                norm = rel.replace("\\", "/").lstrip("/")
                if not norm.startswith("tests/"):
                    raise ValueError(
                        f"caller-supplied test files must live under tests/: {rel!r}")
                p = Path(work) / norm
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            parent_prompt = _PLAN_PROMPT.format(task=task)
        else:
            parent_prompt = _SUITE_AUTHOR_PROMPT.format(task=task)

        # Parent run: author the suite (or plan); initializes the coordinator.
        parent = await agent.run(parent_prompt, deps=deps)
        coordinator = deps.fork_coordinator
        if coordinator is None:
            raise RuntimeError("fork_coordinator not set — is forking enabled on the agent?")

        specs = [
            BranchSpec(label=label, steer=f"{steer}{_STEER_CONTRACT}\n\nTask:\n{task}",
                       budget_usd=per_branch_budget_usd)
            for label, steer in approaches
        ]
        handle = await coordinator.fork(
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
            # ADR-0018 integrity check — BEFORE merge/abort release the overlays.
            tampered = await _tampered_branch_ids(coordinator, handle.fork_id)
            for o in outcomes:
                branches.append(HarnessBranchResult(
                    branch_id=o.branch_id, label=o.branch_label,
                    test_pass_ratio=o.test_pass_ratio, cost_usd=o.cost_usd,
                    turns=o.turns, error_count=o.error_count,
                    preview=(o.final_assistant_message or "")[:200],
                    tests_tampered=o.branch_id in tampered,
                ))
            # ADR-0018 (6.1/6.1a): mergeable iff the UNTAMPERED shared suite
            # fully passed (ratio == 1.0 under the vendor's binary semantics;
            # a granular partial pass would stay unmergeable). Tie-break is
            # stated, not accidental: fewest errors, then cheapest, then
            # original approach order (stable sort) — no judge in selection.
            qualified = [b for b in branches
                         if b.test_pass_ratio == 1.0 and not b.tests_tampered]
            ranked = sorted(
                qualified,
                key=lambda b: (b.error_count,
                               b.cost_usd if b.cost_usd is not None else float("inf")),
            )
            best = ranked[0] if ranked else None
            if best:
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
