"""Phase 4.0 — coverage-first tests for the fork engine (crit prerequisite for
4.5, 4.6, 5.2, 6.1).

`run_forked_viability` had essentially zero behavioral coverage while four later
steps reshape it. These tests pin the CURRENT v1 orchestration behavior with a
deterministic fake coordinator (the vendor `ForkCoordinator` surface used by
forking.py), plus one full offline `TestModel` fork run through the real vendor
machinery (the exit-gate-4 Matrix B field-compare).

Tests marked "V1 PIN — flipped by 4.6" document the defects 4.6 fixes, red-test-
first: they assert the *buggy* current behavior and are rewritten in the 4.6
commit to assert the fix.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from eval_optimizer import forking
from eval_optimizer.schema import HarnessForkReport

ROOT = Path(__file__).resolve().parents[3]
BASELINE_SAMPLE = ROOT / "baseline" / "schemas-v1" / "harness-fork-report-sample.json"


# --------------------------- deterministic fakes ---------------------------
# Shapes mirror the vendor surface forking.py consumes: BranchOutcome fields,
# BranchStatus.state, MergeResult.winner_branch_id, ResolveOutcome.merge_result.

class FakeOutcome:
    def __init__(self, branch_id: str, label: str, ratio: float | None,
                 cost: float | None = 0.01, turns: int = 1, errors: int = 0,
                 msg: str = "ok") -> None:
        self.branch_id = branch_id
        self.branch_label = label
        self.test_pass_ratio = ratio
        self.cost_usd = cost
        self.turns = turns
        self.error_count = errors
        self.final_assistant_message = msg


class FakeStatus:
    def __init__(self, state: str) -> None:
        self.state = state


class FakeMergeResult:
    def __init__(self, winner: str | None) -> None:
        self.winner_branch_id = winner


class FakeResolveOutcome:
    def __init__(self, merge_result: FakeMergeResult | None) -> None:
        self.merge_result = merge_result


class FakeCoordinator:
    """Records every coordinator interaction so tests can assert the exact
    selection path taken (deterministic pick / abort / judge fallback)."""

    def __init__(self, *, outcomes: list[FakeOutcome] | None = None,
                 outcomes_error: Exception | None = None,
                 states: tuple[str, ...] = ("done",),
                 resolve_winner: str | None = None) -> None:
        self._outcomes = outcomes or []
        self._outcomes_error = outcomes_error
        self._states = states
        self._resolve_winner = resolve_winner
        self.calls: list[tuple[str, object]] = []
        self.terminated: list[str] = []

    async def fork(self, specs, *, parent_history, isolation=None,
                   aggregate_budget_usd=None):
        self.calls.append(("fork", len(specs)))

    def inspect_branches(self):
        return [FakeStatus(s) for s in self._states]

    async def branch_outcomes(self):
        if self._outcomes_error is not None:
            raise self._outcomes_error
        return list(self._outcomes)

    async def merge_or_select(self, action: str):
        self.calls.append(("merge_or_select", action))
        if action.startswith("pick:"):
            return FakeMergeResult(action.split(":", 1)[1])
        return FakeMergeResult(None)

    async def resolve(self, strategy=None):
        self.calls.append(("resolve", getattr(strategy, "kind", None)))
        if self._resolve_winner is None:
            return FakeResolveOutcome(None)
        return FakeResolveOutcome(FakeMergeResult(self._resolve_winner))

    async def terminate_branch(self, branch_id: str, *, reason: str | None = None):
        self.terminated.append(branch_id)

    async def aclose(self):
        self.calls.append(("aclose", None))


class FakeResult:
    def all_messages(self):
        return []


class FakeAgent:
    """Stub builder agent: sets the coordinator on deps (as the vendor
    LiveForkCapability.for_run does at run start) and returns a plan result."""

    def __init__(self, coordinator: FakeCoordinator) -> None:
        self._coordinator = coordinator

    async def run(self, prompt, deps=None, **kwargs):
        deps.fork_coordinator = self._coordinator
        return FakeResult()


@pytest.fixture
def fork_env(monkeypatch, tmp_path):
    """Isolate run_forked_viability from the host env: dummy provider key
    (Settings.from_env), scratch TMPDIR for the parent work tree."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))


def _install(monkeypatch, coordinator: FakeCoordinator) -> None:
    monkeypatch.setattr(forking, "_builder_agent", lambda: FakeAgent(coordinator))


# ----------------------- deterministic selection path -----------------------

async def test_deterministic_pick_merges_partial_pass_branch(monkeypatch, fork_env):
    """The `>0` threshold merges a PARTIAL-pass branch as winner (v1 semantics;
    the threshold itself is ADR 6.1a's decision, pinned here as-is)."""
    coord = FakeCoordinator(outcomes=[
        FakeOutcome("b1", "partial", 0.4),
        FakeOutcome("b2", "failing", 0.0),
        FakeOutcome("b3", "no-signal", None),
    ])
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    assert ("merge_or_select", "pick:b1") in coord.calls
    assert report.winner_branch_id == "b1"
    assert report.any_viable is True
    assert [b.branch_id for b in report.branches] == ["b1", "b2", "b3"]
    assert ("aclose", None) in coord.calls


async def test_no_passing_branch_aborts(monkeypatch, fork_env):
    coord = FakeCoordinator(outcomes=[
        FakeOutcome("b1", "failing", 0.0),
        FakeOutcome("b2", "no-signal", None),
    ])
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    assert ("merge_or_select", "abort") in coord.calls
    assert report.winner_branch_id is None
    assert report.any_viable is False
    assert report.winner_dir is None


async def test_save_winner_dir_copies_on_deterministic_win(monkeypatch, fork_env, tmp_path):
    coord = FakeCoordinator(outcomes=[FakeOutcome("b1", "green", 1.0)])
    _install(monkeypatch, coord)
    dst = tmp_path / "winner"
    report = await forking.run_forked_viability("task", save_winner_dir=str(dst))
    assert report.winner_dir == str(dst)
    assert dst.is_dir()


# ----------------------------- fallback path -------------------------------

async def test_selection_exception_falls_back_to_judge(monkeypatch, fork_env):
    """An exception in deterministic selection silently falls back to the judge
    resolve (v1 behavior; 4.5 makes it observable, the policy itself is 6.2)."""
    coord = FakeCoordinator(outcomes_error=RuntimeError("API drift"),
                            resolve_winner="bx")
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    assert ("resolve", "auto") in coord.calls
    assert report.winner_branch_id == "bx"
    assert report.any_viable is True
    assert report.branches == []  # outcomes never materialized on this path


async def test_save_winner_dir_copies_on_fallback(monkeypatch, fork_env, tmp_path):
    """V1 PIN — flipped by 4.6: save_winner_dir copies the work tree even when
    the winner came from the judge fallback (no deterministic merge flushed),
    so the 'winner dir' may not contain the winner's files."""
    coord = FakeCoordinator(outcomes_error=RuntimeError("API drift"),
                            resolve_winner="bx")
    _install(monkeypatch, coord)
    dst = tmp_path / "winner"
    report = await forking.run_forked_viability("task", save_winner_dir=str(dst))
    assert report.winner_dir == str(dst)  # v1 defect: copied on fallback
    assert dst.is_dir()


# ------------------------------ timeout path -------------------------------

async def test_wait_timeout_returns_with_branches_still_running():
    """V1 PIN — flipped by 4.6: on timeout _wait_for_branches returns while
    branches are still running and cancels NOTHING; selection then proceeds
    over live branches."""
    coord = FakeCoordinator(states=("running", "running"))
    statuses = await forking._wait_for_branches(coord, poll_s=0.01, timeout_s=0.03)
    assert [s.state for s in statuses] == ["running", "running"]
    assert coord.terminated == []  # v1 defect: no cancellation on timeout


async def test_wait_returns_when_branches_settle():
    coord = FakeCoordinator(states=("done", "failed"))
    statuses = await forking._wait_for_branches(coord, poll_s=0.01, timeout_s=1.0)
    assert [s.state for s in statuses] == ["done", "failed"]
    assert coord.terminated == []


# ------------------- Matrix B field-compare (exit gate 4) -------------------

def _baseline_sample() -> dict:
    return json.loads(BASELINE_SAMPLE.read_text(encoding="utf-8"))


async def test_report_fields_match_matrix_b_baseline(monkeypatch, fork_env):
    coord = FakeCoordinator(outcomes=[FakeOutcome("b1", "approach-a", 1.0)])
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    sample = _baseline_sample()
    dumped = report.model_dump()
    assert set(sample) <= set(dumped), "Matrix B: report dropped v1 fields"
    assert set(sample["branches"][0]) <= set(dumped["branches"][0])


async def test_full_testmodel_fork_run_matches_matrix_b(monkeypatch, tmp_path):
    """Exit gate 4: a FULL TestModel fork run — real vendor coordinator, real
    branch tasks, real test_command subprocess — whose report field-compares
    against the Matrix B baseline. Offline: TestModel only, trivial test cmd."""
    from pydantic_ai.models.test import TestModel
    from pydantic_deep import LiveForkCapability, create_deep_agent

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))

    test_cmd = f'"{sys.executable}" -c "raise SystemExit(0)"'

    def testmodel_builder():
        return create_deep_agent(
            model=TestModel(call_tools=[]),
            forking=LiveForkCapability(
                test_command=test_cmd, test_timeout_s=60,
                max_branches=3, keep_artifacts=False,
            ),
            include_checkpoints=True,
            web_search=False, web_fetch=False,  # built-ins TestModel rejects
            instructions="Offline fork-run pin. Do not call tools.",
        )

    monkeypatch.setattr(forking, "_builder_agent", testmodel_builder)
    report = await forking.run_forked_viability(
        "offline viability pin",
        approaches=[("a", "steer a"), ("b", "steer b")],
    )
    assert isinstance(report, HarnessForkReport)
    assert len(report.branches) == 2
    sample = _baseline_sample()
    dumped = report.model_dump()
    assert set(sample) <= set(dumped), "Matrix B: report dropped v1 fields"
    for branch in dumped["branches"]:
        assert set(sample["branches"][0]) <= set(branch)
    # both branches ran the trivial passing test command -> deterministic pick
    assert report.winner_branch_id is not None
    assert report.any_viable is True
