"""ADR-0012: requires_approval tool pauses the run into an AG-UI interrupt."""
from __future__ import annotations

import json
import warnings

import pytest
from pydantic_ai import Tool
from pydantic_ai.models.test import TestModel

from agent_web.app import create_app
from helpers import make_settings, post_run, run_input_json

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


async def test_interrupt_emitted_and_tool_not_run(app):
    CALLS.clear()
    async with app.router.lifespan_context(app):
        code, text = await post_run(app, run_input_json("clean up", thread_id="appr"))
    assert code == 200
    assert "RUN_FINISHED" in text
    assert "interrupt" in text.lower(), text[-2000:]
    assert CALLS == []  # tool must NOT have executed before approval


def _sse_events(text: str) -> list[dict]:
    import json as _json

    return [_json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def test_resume_approved_executes_tool(app):
    """Full ADR-0012 approval loop: interrupt -> client approves -> tool runs once."""
    import uuid

    from ag_ui.core import RunAgentInput, UserMessage

    CALLS.clear()
    msg = UserMessage(id="m1", role="user", content="clean up /tmp/x")
    common = dict(messages=[msg], tools=[], context=[], state={}, forwarded_props={})

    async with app.router.lifespan_context(app):
        # Run 1: model proposes the gated tool; run pauses with an interrupt.
        r1 = RunAgentInput(thread_id="resume-t", run_id="r-1", **common)
        code, text = await post_run(app, r1.model_dump_json(by_alias=True))
        assert code == 200
        finished = [e for e in _sse_events(text) if e["type"] == "RUN_FINISHED"][-1]
        interrupts = finished["outcome"]["interrupts"]
        assert interrupts and CALLS == []  # paused, tool NOT executed

        # Run 2: same thread, resume[] approving each interrupt.
        resume = [
            {"interruptId": i["id"], "status": "resolved", "payload": {"approved": True}}
            for i in interrupts
        ]
        r2 = RunAgentInput(
            thread_id="resume-t", run_id=f"r-{uuid.uuid4().hex[:6]}", resume=resume, **common
        )
        code2, text2 = await post_run(app, r2.model_dump_json(by_alias=True))
        assert code2 == 200
        types2 = {e["type"] for e in _sse_events(text2)}
        assert "TOOL_CALL_RESULT" in types2, types2
        assert len(CALLS) == 1  # executed exactly once, after approval
