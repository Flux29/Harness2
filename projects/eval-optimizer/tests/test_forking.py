"""Phase 4.0 — coverage-first tests for the fork engine (crit prerequisite for
4.5, 4.6, 5.2, 6.1).

`run_forked_viability` had essentially zero behavioral coverage while four later
steps reshape it. These tests pin the CURRENT v1 orchestration behavior with a
deterministic fake coordinator (the vendor `ForkCoordinator` surface used by
forking.py), plus one full offline `TestModel` fork run through the real vendor
machinery (the exit-gate-4 Matrix B field-compare).

Tests marked "V1 PIN — flipped by 4.6" document the defects 4.6 fixes, red-test-
first: they assert the *buggy* current behavior and are rewritten in the 4.6
commit to assert the fix. The selection-failure tests assert ADR-0017 semantics
(abort loud, judge never consulted) since that ADR's acceptance.
"""
from __future__ import annotations

import asyncio
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

class FakeHandle:
    fork_id = "fake-fork"


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
    def __init__(self, branch_id: str, state: str) -> None:
        self.id = branch_id
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
        self._statuses = [FakeStatus(f"b{i}", s) for i, s in enumerate(states)]
        self._resolve_winner = resolve_winner
        self.calls: list[tuple[str, object]] = []
        self.terminated: list[str] = []

    async def fork(self, specs, *, parent_history, isolation=None,
                   aggregate_budget_usd=None):
        self.calls.append(("fork", len(specs)))
        self.forked_specs = list(specs)
        return FakeHandle()

    def inspect_branches(self):
        return list(self._statuses)

    async def branch_outcomes(self):
        if self._outcomes_error is not None:
            raise self._outcomes_error
        return list(self._outcomes)

    async def merge_or_select(self, action: str):
        self.calls.append(("merge_or_select", action))
        if not action.startswith("pick:"):
            # Mirror the real vendor API: only 'pick:<id>' is supported. The
            # 4.0 fake wrongly accepted 'abort'; the real coordinator raises —
            # which is how disc-abort-action-unsupported stayed hidden in v1.
            raise ValueError(f"Unsupported merge action: {action!r}.")
        return FakeMergeResult(action.split(":", 1)[1])

    async def abort_fork(self):
        self.calls.append(("abort_fork", None))
        return [s.id for s in self._statuses]

    async def resolve(self, strategy=None):
        self.calls.append(("resolve", getattr(strategy, "kind", None)))
        if self._resolve_winner is None:
            return FakeResolveOutcome(None)
        return FakeResolveOutcome(FakeMergeResult(self._resolve_winner))

    async def terminate_branch(self, branch_id: str, *, reason: str | None = None):
        self.terminated.append(branch_id)
        for s in self._statuses:
            if s.id == branch_id:
                s.state = "terminated"

    async def aclose(self):
        self.calls.append(("aclose", None))


class FakeResult:
    def all_messages(self):
        return []


class FakeAgent:
    """Stub builder agent: sets the coordinator on deps (as the vendor
    LiveForkCapability.for_run does at run start) and returns a plan result.
    Records the parent prompt and the work tree's files at run time so suite-
    provenance tests (ADR-0018) can assert what the parent was asked to do."""

    def __init__(self, coordinator: FakeCoordinator) -> None:
        self._coordinator = coordinator
        self.seen_prompt: str | None = None
        self.work_files: list[str] = []

    async def run(self, prompt, deps=None, **kwargs):
        from pydantic_deep import unwrap_backend

        self.seen_prompt = prompt
        root = Path(unwrap_backend(deps.backend).root_dir)
        self.work_files = sorted(
            p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        deps.fork_coordinator = self._coordinator
        return FakeResult()


@pytest.fixture
def fork_env(monkeypatch, tmp_path):
    """Isolate run_forked_viability from the host env: dummy provider key
    (Settings.from_env), scratch TMPDIR for the parent work tree, and the 5.2
    host-exec acknowledgment (these tests stub or sandbox all execution)."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("EVALOPT_ALLOW_HOST_EXEC", "1")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))


async def test_host_exec_requires_env_acknowledgment(monkeypatch):
    """Phase 5.2 negative test (exit gate 5): without EVALOPT_ALLOW_HOST_EXEC=1
    the fork engine refuses to run — host execution of generated code is an
    explicit configuration, not a docstring disclosure."""
    monkeypatch.delenv("EVALOPT_ALLOW_HOST_EXEC", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    coord = FakeCoordinator()
    _install(monkeypatch, coord)
    with pytest.raises(RuntimeError, match="EVALOPT_ALLOW_HOST_EXEC"):
        await forking.run_forked_viability("task")
    assert coord.calls == []  # refused before ANY fork work started


def _install(monkeypatch, coordinator: FakeCoordinator,
             tampered: set[str] | None = None) -> FakeAgent:
    agent = FakeAgent(coordinator)
    monkeypatch.setattr(forking, "_builder_agent", lambda: agent)

    # Fake coordinators carry no real overlays, so the ADR-0018 integrity
    # check is injected here; the REAL check runs in the E2E tests below.
    async def fake_tampered(coord, fork_id):
        return set(tampered or ())

    monkeypatch.setattr(forking, "_tampered_branch_ids", fake_tampered)
    return agent


# ----------------------- deterministic selection path -----------------------

async def test_untampered_full_pass_merges(monkeypatch, fork_env):
    """ADR-0018: a branch whose UNTAMPERED shared suite fully passed merges;
    failing / no-signal siblings do not compete."""
    coord = FakeCoordinator(outcomes=[
        FakeOutcome("b1", "green", 1.0),
        FakeOutcome("b2", "failing", 0.0),
        FakeOutcome("b3", "no-signal", None),
    ])
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    assert ("merge_or_select", "pick:b1") in coord.calls
    assert report.winner_branch_id == "b1"
    assert report.any_viable is True
    assert report.selection_path == "deterministic"  # 4.5 provenance
    assert [b.branch_id for b in report.branches] == ["b1", "b2", "b3"]
    assert not any(b.tests_tampered for b in report.branches)
    assert ("aclose", None) in coord.calls


async def test_partial_pass_no_longer_merges(monkeypatch, fork_env):
    """ADR-0018 / 6.1a: the merge threshold is ratio == 1.0. v1's `>0` would
    have merged a hypothetical partial pass; now anything short of a full
    shared-suite pass aborts."""
    coord = FakeCoordinator(outcomes=[
        FakeOutcome("b1", "partial", 0.4),
        FakeOutcome("b2", "worse", 0.2),
    ])
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    assert ("abort_fork", None) in coord.calls
    assert report.winner_branch_id is None
    assert report.any_viable is False


async def test_tie_break_fewest_errors_then_cost(monkeypatch, fork_env):
    """ADR-0018: ranking among full passes is STATED, not accidental — fewest
    errors, then lowest cost. v1's stable sort made the first-listed approach
    win every tie; this pins that the first-listed branch loses on merits."""
    coord = FakeCoordinator(outcomes=[
        FakeOutcome("b1", "first-listed", 1.0, errors=2, cost=0.01),
        FakeOutcome("b2", "clean-costly", 1.0, errors=0, cost=0.09),
        FakeOutcome("b3", "clean-cheap", 1.0, errors=0, cost=0.02),
    ])
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    assert report.winner_branch_id == "b3"  # 0 errors, cheaper than b2
    assert ("merge_or_select", "pick:b3") in coord.calls


async def test_tampered_branch_disqualified(monkeypatch, fork_env):
    """ADR-0018 integrity: a full-pass branch that touched the shared suite is
    disqualified; an honest full pass wins even at higher cost."""
    coord = FakeCoordinator(outcomes=[
        FakeOutcome("b1", "cheater", 1.0, errors=0, cost=0.01),
        FakeOutcome("b2", "honest", 1.0, errors=1, cost=0.05),
    ])
    _install(monkeypatch, coord, tampered={"b1"})
    report = await forking.run_forked_viability("task")
    assert report.winner_branch_id == "b2"
    by_id = {b.branch_id: b for b in report.branches}
    assert by_id["b1"].tests_tampered is True
    assert by_id["b2"].tests_tampered is False


async def test_all_passes_tampered_aborts(monkeypatch, fork_env):
    coord = FakeCoordinator(outcomes=[FakeOutcome("b1", "cheater", 1.0)])
    _install(monkeypatch, coord, tampered={"b1"})
    report = await forking.run_forked_viability("task")
    assert ("abort_fork", None) in coord.calls
    assert report.winner_branch_id is None
    assert report.any_viable is False
    assert report.branches[0].tests_tampered is True


# ------------------------ suite provenance (ADR-0018) ------------------------

async def test_caller_supplied_suite_lands_in_shared_prefix(monkeypatch, fork_env):
    """With tests= supplied, the suite exists in the work tree BEFORE the
    parent run (the shared prefix) and the parent is asked only to plan."""
    coord = FakeCoordinator(outcomes=[FakeOutcome("b1", "green", 1.0)])
    agent = _install(monkeypatch, coord)
    await forking.run_forked_viability(
        "task", tests={"tests/test_contract.py": "def test_ok():\n    assert True\n"})
    assert "tests/test_contract.py" in agent.work_files
    assert "implementation plan" in (agent.seen_prompt or "")
    assert "write ONLY a pytest test suite" not in (agent.seen_prompt or "")


async def test_parent_authors_suite_when_none_supplied(monkeypatch, fork_env):
    coord = FakeCoordinator(outcomes=[FakeOutcome("b1", "green", 1.0)])
    agent = _install(monkeypatch, coord)
    await forking.run_forked_viability("task")
    assert "write ONLY a pytest test suite" in (agent.seen_prompt or "")
    # and every branch steer carries the do-not-touch-tests contract
    assert all("disqualified (ADR-0018)" in s.steer for s in coord.forked_specs)


async def test_caller_supplied_suite_must_live_under_tests(monkeypatch, fork_env):
    coord = FakeCoordinator()
    _install(monkeypatch, coord)
    with pytest.raises(ValueError, match="must live under tests/"):
        await forking.run_forked_viability(
            "task", tests={"src/evil.py": "print('not a test')"})
    assert coord.calls == []  # rejected before any fork work


async def test_no_passing_branch_aborts(monkeypatch, fork_env):
    """disc-abort-action-unsupported: the no-passing-branch path must GENUINELY
    abort via abort_fork(). v1 sent the unsupported 'abort' action to
    merge_or_select, whose ValueError fell into the bare except and let the
    judge quietly merge a winner on the abort path."""
    coord = FakeCoordinator(outcomes=[
        FakeOutcome("b1", "failing", 0.0),
        FakeOutcome("b2", "no-signal", None),
    ], resolve_winner="should-never-be-consulted")
    _install(monkeypatch, coord)
    report = await forking.run_forked_viability("task")
    assert ("abort_fork", None) in coord.calls
    assert ("resolve", "auto") not in coord.calls  # judge NOT consulted on abort
    assert report.winner_branch_id is None
    assert report.any_viable is False
    assert report.winner_dir is None
    assert report.selection_path is None  # 4.5 provenance: no winner, no path


async def test_save_winner_dir_copies_on_deterministic_win(monkeypatch, fork_env, tmp_path):
    coord = FakeCoordinator(outcomes=[FakeOutcome("b1", "green", 1.0)])
    _install(monkeypatch, coord)
    dst = tmp_path / "winner"
    report = await forking.run_forked_viability("task", save_winner_dir=str(dst))
    assert report.winner_dir == str(dst)
    assert dst.is_dir()


# -------------------- selection-failure path (ADR-0017) --------------------

async def test_selection_exception_aborts_loud(monkeypatch, fork_env, caplog):
    """ADR-0017 (plan 6.2): an exception in deterministic selection ABORTS the
    fork fail-loud — logged with traceback, branches cancelled via
    abort_fork(), original exception re-raised. The judge is never consulted
    (v1's silent fallback violated ADR-0011's mandate and masked
    disc-abort-action-unsupported for the repo's entire life)."""
    import logging

    coord = FakeCoordinator(outcomes_error=RuntimeError("API drift"),
                            resolve_winner="should-never-be-consulted")
    _install(monkeypatch, coord)
    with caplog.at_level(logging.WARNING, logger="eval_optimizer.forking"):
        with pytest.raises(RuntimeError, match="API drift"):
            await forking.run_forked_viability("task")
    assert ("abort_fork", None) in coord.calls   # branches cancelled first
    assert not any(name == "resolve" for name, _ in coord.calls)
    assert ("aclose", None) in coord.calls       # finally cleanup still ran
    logs = [r for r in caplog.records if "aborting fork" in r.message]
    assert logs, "ADR-0017: the selection failure must be logged"
    assert logs[0].exc_info is not None          # traceback attached
    assert "API drift" in str(logs[0].exc_info[1])


async def test_selection_exception_never_materializes_winner_dir(
        monkeypatch, fork_env, tmp_path):
    """ADR-0017 + 4.6: a failed selection can never mint a winner dir — the
    exception propagates before any copy could happen."""
    coord = FakeCoordinator(outcomes_error=RuntimeError("API drift"))
    _install(monkeypatch, coord)
    dst = tmp_path / "winner"
    with pytest.raises(RuntimeError, match="API drift"):
        await forking.run_forked_viability("task", save_winner_dir=str(dst))
    assert not dst.exists()


# ------------------------------ timeout path -------------------------------

async def test_wait_timeout_cancels_outstanding_branches():
    """4.6 FLIP of the 4.0 v1 pin: on timeout _wait_for_branches explicitly
    terminates every still-running branch BEFORE returning for selection
    (v1 returned with branches live and selected over them)."""
    coord = FakeCoordinator(states=("running", "done", "running"))
    statuses = await forking._wait_for_branches(coord, poll_s=0.01, timeout_s=0.03)
    assert coord.terminated == ["b0", "b2"]  # only the outstanding ones
    assert [s.state for s in statuses] == ["terminated", "done", "terminated"]


async def test_wait_returns_when_branches_settle():
    coord = FakeCoordinator(states=("done", "failed"))
    statuses = await forking._wait_for_branches(coord, poll_s=0.01, timeout_s=1.0)
    assert [s.state for s in statuses] == ["done", "failed"]
    assert coord.terminated == []


async def test_e2e_fork_timeout_cancels_real_branches(monkeypatch, tmp_path):
    """Exit-gate-4 'fork-timeout' E2E: REAL vendor coordinator, branch tasks
    genuinely hung (a FunctionModel that sleeps on every post-parent call), a
    forced short wait window. The timeout path must terminate the live branch
    tasks and still return a clean no-winner report — v1 would have selected
    over the still-running branches."""
    import time

    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel
    from pydantic_deep import LiveForkCapability, create_deep_agent

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("EVALOPT_ALLOW_HOST_EXEC", "1")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))

    calls = {"n": 0}

    async def model_fn(messages: list, info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] > 1:  # parent plan returns instantly; branches hang
            await asyncio.sleep(30)
        return ModelResponse(parts=[TextPart("plan: do the thing")])

    def hung_builder():
        return create_deep_agent(
            model=FunctionModel(model_fn),
            forking=LiveForkCapability(
                test_command=f'"{sys.executable}" -c "raise SystemExit(1)"',
                test_timeout_s=30, max_branches=3, keep_artifacts=False,
            ),
            include_checkpoints=True,
            web_search=False, web_fetch=False,
            instructions="Timeout E2E pin.",
        )

    monkeypatch.setattr(forking, "_builder_agent", hung_builder)

    real_wait = forking._wait_for_branches

    async def short_wait(coordinator, poll_s: float = 0.05, timeout_s: float = 0.3):
        return await real_wait(coordinator, poll_s=poll_s, timeout_s=timeout_s)

    monkeypatch.setattr(forking, "_wait_for_branches", short_wait)

    start = time.monotonic()
    report = await forking.run_forked_viability(
        "timeout pin", approaches=[("a", "steer a"), ("b", "steer b")],
    )
    elapsed = time.monotonic() - start
    # Branches slept 30s; the run must NOT have waited them out — the timeout
    # path terminated them (real asyncio.Task cancellation via the vendor's
    # terminate_branch) and selection saw only settled branches.
    assert elapsed < 20, f"timeout path did not cancel hung branches ({elapsed:.1f}s)"
    assert report.winner_branch_id is None
    assert report.any_viable is False
    assert report.selection_path is None
    assert report.winner_dir is None


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
    monkeypatch.setenv("EVALOPT_ALLOW_HOST_EXEC", "1")
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
        tests={"tests/test_contract.py": "def test_ok():\n    assert True\n"},
    )
    assert isinstance(report, HarnessForkReport)
    assert len(report.branches) == 2
    sample = _baseline_sample()
    dumped = report.model_dump()
    assert set(sample) <= set(dumped), "Matrix B: report dropped v1 fields"
    for branch in dumped["branches"]:
        assert set(sample["branches"][0]) <= set(branch)
    # both branches ran the trivial passing test command -> deterministic pick;
    # the REAL ADR-0018 integrity check ran over the live overlays (TestModel
    # branches write nothing, so both are untampered).
    assert not any(b.tests_tampered for b in report.branches)
    assert report.winner_branch_id is not None
    assert report.any_viable is True


async def test_e2e_tampering_branch_disqualified_via_real_overlays(monkeypatch, tmp_path):
    """ADR-0018 integrity E2E through the REAL vendor machinery: a branch that
    writes into tests/ (via a real write_file tool call landing in its real
    copy-on-write overlay) is detected by the public diff API and disqualified,
    while its honest sibling — identical suite outcome — wins the merge."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel
    from pydantic_deep import LiveForkCapability, create_deep_agent

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("EVALOPT_ALLOW_HOST_EXEC", "1")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))

    async def model_fn(messages: list, info: AgentInfo) -> ModelResponse:
        joined = "".join(str(m) for m in messages)
        has_tool_return = any(
            part.__class__.__name__ == "ToolReturnPart"
            for m in messages for part in getattr(m, "parts", []))
        if "TAMPER-THE-SUITE" in joined and not has_tool_return:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="write_file",
                args={"path": "tests/test_hacked.py",
                      "content": "def test_free_win():\n    assert True\n"},
            )])
        return ModelResponse(parts=[TextPart("done")])

    def tamper_builder():
        return create_deep_agent(
            model=FunctionModel(model_fn),
            forking=LiveForkCapability(
                test_command=f'"{sys.executable}" -c "raise SystemExit(0)"',
                test_timeout_s=30, max_branches=3, keep_artifacts=False,
            ),
            include_checkpoints=True,
            web_search=False, web_fetch=False,
            instructions="Integrity E2E pin.",
        )

    monkeypatch.setattr(forking, "_builder_agent", tamper_builder)
    report = await forking.run_forked_viability(
        "integrity pin",
        approaches=[("honest", "Do nothing further."),
                    ("cheater", "TAMPER-THE-SUITE")],
        tests={"tests/test_contract.py": "def test_ok():\n    assert True\n"},
    )
    by_label = {b.label: b for b in report.branches}
    assert by_label["cheater"].tests_tampered is True
    assert by_label["honest"].tests_tampered is False
    # identical (trivially passing) suite outcome — integrity decides it:
    assert report.winner_branch_id == by_label["honest"].branch_id
    assert report.any_viable is True
