"""ADR-0015: the full-featured agent builds; ADR-0012 risk 1 resolution holds."""
from __future__ import annotations

import warnings

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import DeferredToolRequests

from agent_web.agent import build_agent
from helpers import make_settings


def test_agent_builds_with_full_flags(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        agent = build_agent(make_settings(tmp_path), model=TestModel())
    assert isinstance(agent, Agent)
    assert DeferredToolRequests in list(agent.output_type)  # interrupts supported


async def _tool_names(agent, model: TestModel) -> set[str]:
    """Run once and read the tool schemas the model was actually offered."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pydantic_deep import create_default_deps

        await agent.run("hi", deps=create_default_deps())
    params = model.last_model_request_parameters
    return {t.name for t in params.function_tools} if params else set()


async def test_fork_disabled_by_default_no_fork_toolset(tmp_path):
    """Phase 5.2 negative test (exit gate 5): with the FORKING flag off — the
    code default — the agent's toolset carries NO fork tools, so LLM-generated
    code cannot reach host execution through the fork path."""
    model = TestModel(call_tools=[])
    agent = build_agent(make_settings(tmp_path), model=model)
    names = await _tool_names(agent, model)
    assert names, "expected the model to be offered the base toolset"
    fork_tools = {n for n in names if "fork" in n or n == "terminate_branch"}
    assert fork_tools == set(), f"fork tools present with FORKING off: {fork_tools}"


async def test_fork_flag_enables_fork_toolset(tmp_path):
    from dataclasses import replace

    model = TestModel(call_tools=[])
    agent = build_agent(replace(make_settings(tmp_path), forking=True), model=model)
    names = await _tool_names(agent, model)
    assert "fork_run" in names, f"FORKING=1 must add the fork toolset, got: {sorted(names)[:20]}"
