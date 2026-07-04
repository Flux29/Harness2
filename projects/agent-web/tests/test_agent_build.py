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
