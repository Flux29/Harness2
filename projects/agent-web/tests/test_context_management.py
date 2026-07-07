"""feat-context-budget: sliding-window context reduction (cost control).

Prompt caching is unavailable on the GLM/OpenRouter route (OpenRouter forwards
cache_control only to Anthropic/Google), so per-turn cost is controlled by
sending fewer tokens. These tests pin the deterministic plumbing: the
processor the settings produce actually trims, and build_agent wires it.
"""
from __future__ import annotations

import warnings
from dataclasses import replace

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.test import TestModel

from agent_web.agent import _history_processors
from agent_web.app import create_app
from helpers import make_settings


def _synthetic_history(n: int):
    """n alternating request/response messages, each a few tokens."""
    msgs = []
    for i in range(n):
        if i % 2 == 0:
            msgs.append(ModelRequest(parts=[UserPromptPart(content=f"user turn {i} " * 8)]))
        else:
            msgs.append(ModelResponse(parts=[TextPart(content=f"assistant turn {i} " * 8)]))
    return msgs


async def test_sliding_window_trims_when_over_trigger(tmp_path):
    # A low trigger so a modest synthetic history crosses it deterministically.
    settings = replace(
        make_settings(tmp_path),
        history_window=True,
        history_window_trigger_tokens=200,
        history_window_keep_messages=10,
    )
    procs = _history_processors(settings)
    assert len(procs) == 1
    proc = procs[0]

    history = _synthetic_history(200)
    trimmed = await proc(history)  # SlidingWindowProcessor.__call__ is async
    # keep_head(1) + keep window(10); far fewer than 200.
    assert len(trimmed) < len(history)
    assert len(trimmed) <= 1 + 10 + 2  # small slack for boundary handling
    # The FIRST turn (system/task anchor) is preserved by keep_head.
    assert trimmed[0] is history[0]
    # The most recent turn survives.
    assert trimmed[-1] is history[-1]


async def test_sliding_window_noop_under_trigger(tmp_path):
    settings = replace(make_settings(tmp_path), history_window=True,
                       history_window_trigger_tokens=100_000)
    proc = _history_processors(settings)[0]
    history = _synthetic_history(20)
    assert await proc(history) == history  # nothing trimmed below the trigger


def test_history_window_disabled(tmp_path):
    settings = replace(make_settings(tmp_path), history_window=False)
    assert _history_processors(settings) == []


async def test_build_agent_wires_context_budget(tmp_path):
    """build_agent must construct with the calibrated budget + processor
    without error (the wiring regression: proves create_deep_agent accepts
    context_manager_max_tokens / history_processors / on_context_update)."""
    settings = replace(make_settings(tmp_path), context_manager_max_tokens=120_000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        app = create_app(settings=settings, model=TestModel(call_tools=[]))
    async with app.router.lifespan_context(app):
        assert app.state.agent is not None
