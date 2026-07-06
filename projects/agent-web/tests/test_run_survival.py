"""feat-run-survival: an agent run outlives its client (ISSUE-4 live find).

Before the background-tee, an SSE disconnect (page reload, thread switch)
cancelled the response generator mid-stream and the run died with history
unsaved — a live fork run was lost exactly this way. Now the run executes in
a background task; disconnect cancels only the tee.
"""
from __future__ import annotations

import asyncio
import warnings

import pytest
from pydantic_ai import Tool
from pydantic_ai.models.test import TestModel

from agent_web.app import create_app
from helpers import make_settings, post_run, run_input_json
from test_threads_api import get_json


async def slow_step(note: str) -> str:
    """Take a moment before answering (keeps the run alive past a disconnect)."""
    await asyncio.sleep(0.6)
    return f"done: {note}"


@pytest.fixture()
def app(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return create_app(
            settings=make_settings(tmp_path),
            model=TestModel(call_tools=["slow_step"]),
            extra_tools=(Tool(slow_step),),
        )


async def test_run_survives_client_disconnect(app, tmp_path):
    # httpx's ASGITransport buffers the app response, so a "partial read"
    # cannot model a disconnect; cancelling the in-flight request task does —
    # it propagates cancellation into the response stream exactly like a
    # dropped SSE connection (reload / thread switch).
    import contextlib

    async with app.router.lifespan_context(app):
        post_task = asyncio.create_task(
            post_run(app, run_input_json("survive me", thread_id="t-surv")))

        # Let the run reach the slow tool, then verify it is visibly in flight.
        await asyncio.sleep(0.25)
        assert app.state.active_runs, "run should be registered while in flight"
        code, body = await get_json(app, "/threads")
        assert code == 200
        row = next((t for t in body["threads"] if t["id"] == "t-surv"), None)
        if row is not None:  # listed only once a first save exists; flag must agree
            assert row["running"] is True

        # The client vanishes mid-run.
        post_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await post_task

        # The run completes and SAVES despite the dead client.
        hist = tmp_path / "state" / "history" / "t-surv.json"
        for _ in range(200):
            if hist.exists() and not app.state.active_runs:
                break
            await asyncio.sleep(0.05)
        assert hist.exists(), "history was not saved after client disconnect"
        assert not app.state.active_runs

        code, body = await get_json(app, "/threads")
        row = next(t for t in body["threads"] if t["id"] == "t-surv")
        assert row["running"] is False
        assert row["message_count"] >= 2


async def test_normal_run_still_streams_fully(app, tmp_path):
    """Tee regression: an attached client still receives the whole stream."""
    async with app.router.lifespan_context(app):
        code, text = await post_run(app, run_input_json("stay attached", thread_id="t-full"))
    assert code == 200
    assert "RUN_STARTED" in text and "RUN_FINISHED" in text
    assert (tmp_path / "state" / "history" / "t-full.json").exists()
    assert not app.state.active_runs
