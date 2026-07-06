"""feat-thread-persistence (ISSUE-4): GET /threads + GET /threads/{id}/messages.

Offline E2E over the real ASGI app: the list index, transcript payloads via
AGUIAdapter.dump_messages, pending-interrupt derivation (parity-pinned against
a live paused run), the GET guard posture, and the dual-write read path.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import replace

import pytest
from pydantic_ai import Tool
from pydantic_ai.models.test import TestModel

from agent_web import history
from agent_web.app import create_app
from helpers import make_settings, post_run, run_input_json


def _make_app(settings, model=None, extra_tools=()):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return create_app(settings=settings, model=model or TestModel(call_tools=[]),
                          extra_tools=tuple(extra_tools))


@pytest.fixture()
def app(tmp_path):
    return _make_app(make_settings(tmp_path))


async def get_json(app, path: str, headers: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get(path, headers=headers or {})
        return r.status_code, (r.json() if r.content else None)


def _sse_events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


# --- listing -----------------------------------------------------------------


async def test_threads_list_empty(app):
    async with app.router.lifespan_context(app):
        code, body = await get_json(app, "/threads")
    assert code == 200
    assert body == {"threads": []}


async def test_threads_list_after_runs(app):
    async with app.router.lifespan_context(app):
        await post_run(app, run_input_json("first prompt about apples", thread_id="t-alpha"))
        await post_run(app, run_input_json("second prompt about pears", thread_id="t-beta"))
        code, body = await get_json(app, "/threads")
    assert code == 200
    listed = {t["id"]: t for t in body["threads"]}
    assert set(listed) == {"t-alpha", "t-beta"}
    alpha = listed["t-alpha"]
    assert alpha["title"] == "first prompt about apples"
    assert alpha["message_count"] >= 2
    assert alpha["has_pending_interrupts"] is False
    assert alpha["running"] is False
    assert alpha["updated_at"]
    # newest-first ordering (beta ran after alpha)
    assert body["threads"][0]["id"] == "t-beta"


async def test_index_upserted_on_save(app):
    """The hash-slug gap: an exotic id sanitizes to a hash-suffixed slug, but
    the index records — and the list serves — the ORIGINAL thread id."""
    exotic = "user/exotic@id!"
    async with app.router.lifespan_context(app):
        await post_run(app, run_input_json("exotic thread", thread_id=exotic))
        code, body = await get_json(app, "/threads")
    assert code == 200
    assert [t["id"] for t in body["threads"]] == [exotic]


async def test_index_regenerates_when_missing(app, tmp_path):
    """Delete the index -> the list rebuilds from disk, INCLUDING a legacy v1
    workspaces/<slug>/history.json copy (the pre-5.1 dormant-thread backfill)."""
    async with app.router.lifespan_context(app):
        await post_run(app, run_input_json("kept thread", thread_id="t-keep"))
        # Seed a pre-5.1 dormant thread: a v1 workspace copy with NO state copy.
        legacy = tmp_path / "workspaces" / "legacy-old" / "history.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes((tmp_path / "state" / "history" / "t-keep.json").read_bytes())
        index = tmp_path / "state" / "threads-index.json"
        index.unlink()
        code, body = await get_json(app, "/threads")
    assert code == 200
    assert {t["id"] for t in body["threads"]} == {"t-keep", "legacy-old"}
    assert index.exists()  # regenerated and persisted


# --- transcript payloads -------------------------------------------------------


async def test_thread_messages_round_trip(tmp_path):
    """dump_messages end-to-end: user content, camelCase assistant toolCalls,
    and the tool-result message all present in the payload."""
    calls: list[str] = []

    def echo_tool(text: str) -> str:
        """Echo the text back."""
        calls.append(text)
        return f"echo: {text}"

    app = _make_app(make_settings(tmp_path),
                    model=TestModel(call_tools=["echo_tool"]),
                    extra_tools=(Tool(echo_tool),))
    async with app.router.lifespan_context(app):
        code, _ = await post_run(app, run_input_json("round trip", thread_id="t-rt"))
        assert code == 200
        code, body = await get_json(app, "/threads/t-rt/messages")
    assert code == 200
    assert body["id"] == "t-rt"
    assert body["interrupts"] == []
    roles = [m["role"] for m in body["messages"]]
    assert "user" in roles and "assistant" in roles and "tool" in roles
    user = next(m for m in body["messages"] if m["role"] == "user")
    assert user["content"] == "round trip"
    with_calls = [m for m in body["messages"] if m.get("toolCalls")]
    assert with_calls, f"no assistant toolCalls in payload roles={roles}"
    call = with_calls[0]["toolCalls"][0]
    assert call["function"]["name"] == "echo_tool"
    assert calls  # the tool really ran


async def test_thread_messages_unknown_404(app):
    async with app.router.lifespan_context(app):
        code, body = await get_json(app, "/threads/never-existed/messages")
    assert code == 404
    assert body == {"error": "unknown thread"}


# --- pending-interrupt derivation (the drift pin) ---------------------------


async def test_pending_interrupt_parity(tmp_path):
    """The derived interrupt must match the LIVE one the wire emitted for the
    same paused run (id `int-<toolCallId>`, toolCallId, reason) — this is the
    drift pin for hard-coding the private `int-` prefix."""
    import uuid

    from ag_ui.core import RunAgentInput, UserMessage

    def dangerous_cleanup(path: str) -> str:
        """Delete a workspace path (approval-gated)."""
        return f"cleaned {path}"

    app = _make_app(make_settings(tmp_path),
                    model=TestModel(call_tools=["dangerous_cleanup"]),
                    extra_tools=(Tool(dangerous_cleanup, requires_approval=True),))
    common = dict(tools=[], context=[], state={}, forwarded_props={})
    msg = UserMessage(id="m1", role="user", content="clean up /tmp/x")

    async with app.router.lifespan_context(app):
        # Run 1: pauses on approval; capture the LIVE interrupt from the wire.
        r1 = RunAgentInput(thread_id="t-int", run_id="r-1", messages=[msg], **common)
        code, text = await post_run(app, r1.model_dump_json(by_alias=True))
        assert code == 200
        finished = [e for e in _sse_events(text) if e["type"] == "RUN_FINISHED"][-1]
        live = finished["outcome"]["interrupts"]
        assert live

        code, body = await get_json(app, "/threads/t-int/messages")
        assert code == 200
        derived = body["interrupts"]
        assert len(derived) == len(live) == 1
        assert derived[0]["id"] == live[0]["id"]
        assert derived[0]["toolCallId"] == live[0]["toolCallId"]
        assert derived[0]["reason"] == live[0]["reason"]
        assert derived[0]["id"] == f"int-{derived[0]['toolCallId']}"

        code, body = await get_json(app, "/threads")
        assert next(t for t in body["threads"] if t["id"] == "t-int")[
            "has_pending_interrupts"] is True

        # Run 2: approve -> the pause resolves; derivation must go quiet.
        resume = [{"interruptId": live[0]["id"], "status": "resolved",
                   "payload": {"approved": True}}]
        r2 = RunAgentInput(thread_id="t-int", run_id=f"r-{uuid.uuid4().hex[:6]}",
                           resume=resume, messages=[msg], **common)
        code, _ = await post_run(app, r2.model_dump_json(by_alias=True))
        assert code == 200
        code, body = await get_json(app, "/threads/t-int/messages")
        assert body["interrupts"] == []
        code, body = await get_json(app, "/threads")
        assert next(t for t in body["threads"] if t["id"] == "t-int")[
            "has_pending_interrupts"] is False


# --- guard posture -----------------------------------------------------------


async def test_guard_get_403s(tmp_path):
    settings = replace(make_settings(tmp_path), agent_token="s3cret")
    app = _make_app(settings)
    async with app.router.lifespan_context(app):
        # bearer required when AGENT_TOKEN set; GETs send no content-type.
        code, _ = await get_json(app, "/threads")
        assert code == 403
        code, _ = await get_json(app, "/threads",
                                 headers={"authorization": "Bearer s3cret"})
        assert code == 200

        # POST /agent regression: content-type rule still enforced post-refactor.
        import httpx
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/agent", content=run_input_json("x"),
                                  headers={"authorization": "Bearer s3cret",
                                           "content-type": "text/plain"})
        assert r.status_code == 403

    # Loopback-Host check applies to the GETs too (synthetic host 'test').
    strict = replace(make_settings(tmp_path), require_loopback_host=True)
    app2 = _make_app(strict)
    async with app2.router.lifespan_context(app2):
        code, _ = await get_json(app2, "/threads")
    assert code == 403


# --- dual-write window read path ----------------------------------------------


async def test_dual_write_read_path(tmp_path):
    """Window open: single-thread reads must come from the v1 workspace copy
    (authoritative during the window), while the state file keeps serving as
    the listing index."""
    settings = replace(make_settings(tmp_path), history_dual_write=True)
    app = _make_app(settings)
    async with app.router.lifespan_context(app):
        code, _ = await post_run(app, run_input_json("window prompt", thread_id="t-dw"))
        assert code == 200
        # Tamper the STATE copy; the workspace copy stays authoritative.
        state_copy = tmp_path / "state" / "history" / "t-dw.json"
        tampered = history.ModelMessagesTypeAdapter.validate_json(state_copy.read_bytes())
        state_copy.write_bytes(
            history.ModelMessagesTypeAdapter.dump_json(tampered[:1], indent=2))
        code, body = await get_json(app, "/threads/t-dw/messages")
        assert code == 200
        # v1 copy has the full exchange; the tampered state copy has 1 message.
        assert len(body["messages"]) > 1
        code, body = await get_json(app, "/threads")
        assert [t["id"] for t in body["threads"]] == ["t-dw"]
