"""disc-rehydrated-interrupt-resume: resuming a REHYDRATED approval interrupt.

The manual-thread-persistence feature replays a paused approval after reload
(PersistentAgent.connect -> RUN_FINISHED interrupt outcome). When the user
answers, the frontend re-sends its dump_messages snapshot as run input.

Two changes in app.py harden this:
  1. RECONCILIATION — on resume, the server-authoritative history is the
     single source (the client snapshot is dropped), aligning with ADR-0012.
     This is defensive correctness: the live GLM UserError (`message history
     does not contain any unprocessed tool calls`) is GLM-message-shape
     dependent (real ThinkingParts carry provider signatures that round-trip
     through dump_messages differently than TestModel's clean parts) and is
     NOT reproducible offline — so the two rehydrated-path tests below are
     REGRESSION tests (the path resolves correctly), not red-first repros.
  2. GUARD — a resume whose thread has no matching pending tool call (cleared
     thread, already resolved) is a real, offline-reproducible crash: without
     the guard the run emits RUN_ERROR; with it, a clean finish. That is the
     red/green test at the bottom.
"""
from __future__ import annotations

import json
import uuid
import warnings

import httpx
import pytest
from ag_ui.core import RunAgentInput, UserMessage
from pydantic_ai import Tool
from pydantic_ai.models.test import TestModel

from agent_web.app import create_app
from helpers import make_settings, post_run

CALLS: list[str] = []


def dangerous_cleanup(path: str) -> str:
    """Delete a workspace path (approval-gated)."""
    CALLS.append(path)
    return f"cleaned {path}"


@pytest.fixture()
def app(tmp_path):
    tool = Tool(dangerous_cleanup, requires_approval=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return create_app(
            settings=make_settings(tmp_path),
            model=TestModel(call_tools=["dangerous_cleanup"]),
            extra_tools=(tool,),
        )


def _sse_events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def _get_json(app, path: str):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get(path)
        return r.status_code, r.json()


async def _pause_on_approval(app, thread_id: str) -> list[dict]:
    """Run 1: propose the gated tool; return the live interrupts."""
    msg = UserMessage(id="m1", role="user", content="clean up /tmp/x")
    r1 = RunAgentInput(thread_id=thread_id, run_id="r-1", messages=[msg],
                       tools=[], context=[], state={}, forwarded_props={})
    code, text = await post_run(app, r1.model_dump_json(by_alias=True))
    assert code == 200
    finished = [e for e in _sse_events(text) if e["type"] == "RUN_FINISHED"][-1]
    interrupts = finished["outcome"]["interrupts"]
    assert interrupts and CALLS == []  # paused, tool NOT executed
    return interrupts


async def _resume_rehydrated(app, thread_id, interrupts, approved: bool):
    """Run 2 the REHYDRATED way: resume[] PLUS the GET /messages snapshot as
    run_input.messages (what the frontend re-sends after a reload)."""
    _, payload = await _get_json(app, f"/threads/{thread_id}/messages")
    resume = [{"interruptId": i["id"], "status": "resolved",
               "payload": {"approved": approved}} for i in interrupts]
    r2 = RunAgentInput(
        thread_id=thread_id, run_id=f"r-{uuid.uuid4().hex[:6]}",
        messages=payload["messages"], resume=resume,
        tools=[], context=[], state={}, forwarded_props={},
    )
    return await post_run(app, r2.model_dump_json(by_alias=True))


async def test_rehydrated_resume_approve_executes_once(app):
    CALLS.clear()
    async with app.router.lifespan_context(app):
        interrupts = await _pause_on_approval(app, "rehy-appr")
        code, text = await _resume_rehydrated(app, "rehy-appr", interrupts, approved=True)
    assert code == 200
    types = {e["type"] for e in _sse_events(text)}
    assert "TOOL_CALL_RESULT" in types, types
    assert len(CALLS) == 1  # executed exactly once, no UserError


async def test_rehydrated_resume_deny_resolves(app):
    CALLS.clear()
    async with app.router.lifespan_context(app):
        interrupts = await _pause_on_approval(app, "rehy-deny")
        code, text = await _resume_rehydrated(app, "rehy-deny", interrupts, approved=False)
    assert code == 200
    assert CALLS == []  # denied -> never executed, and no crash
    # The pending flag clears once resolved.
    async with app.router.lifespan_context(app):
        _, body = await _get_json(app, "/threads")
    row = next(t for t in body["threads"] if t["id"] == "rehy-deny")
    assert row["has_pending_interrupts"] is False


async def test_resume_on_cleared_thread_is_clean(app, tmp_path):
    """GUARD (the real red/green): a resume whose history was cleared between
    reload and answer must finish cleanly — WITHOUT the guard the run emits a
    RUN_ERROR (pydantic-ai 'message history is empty'); WITH it, no error."""
    CALLS.clear()
    async with app.router.lifespan_context(app):
        interrupts = await _pause_on_approval(app, "rehy-gone")
        # Simulate the thread being cleared between reload and answer.
        (tmp_path / "state" / "history" / "rehy-gone.json").unlink()
        resume = [{"interruptId": i["id"], "status": "resolved",
                   "payload": {"approved": True}} for i in interrupts]
        r2 = RunAgentInput(thread_id="rehy-gone", run_id="r-2", messages=[],
                           resume=resume, tools=[], context=[], state={},
                           forwarded_props={})
        code, text = await post_run(app, r2.model_dump_json(by_alias=True))
    assert code == 200
    types = {e["type"] for e in _sse_events(text)}
    assert "RUN_ERROR" not in types, f"stale resume crashed the run: {types}"
    assert CALLS == []  # the gated tool never ran for a thread with no state
