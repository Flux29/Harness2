"""End-to-end over the real ASGI app: AG-UI in, SSE events out. No mocks of
our own code — TestModel is the only substitution (deterministic model)."""
from __future__ import annotations

import json
import warnings

import pytest
from pydantic_ai.models.test import TestModel

from agent_web.app import create_app
from helpers import make_settings, post_run, run_input_json


@pytest.fixture()
def app(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return create_app(settings=make_settings(tmp_path), model=TestModel(call_tools=[]))


async def test_sse_event_stream_shape(app):
    async with app.router.lifespan_context(app):
        code, text = await post_run(app, run_input_json("hello"))
    assert code == 200
    assert "RUN_STARTED" in text and "RUN_FINISHED" in text
    assert "TEXT_MESSAGE" in text  # text deltas streamed
    assert text.lstrip().startswith("data:")  # SSE framing


async def test_invalid_input_is_422(app):
    async with app.router.lifespan_context(app):
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/agent", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422


async def test_422_body_is_json_object(app):
    """Phase 3.2: the error body is the actual JSON error object, not a JSON
    string literal. json.loads(body) must yield a list/dict, never a str."""
    async with app.router.lifespan_context(app):
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/agent", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422
    loaded = json.loads(r.text)
    assert isinstance(loaded, (list, dict)), f"422 body double-encoded: got {type(loaded).__name__}"


async def test_history_persisted_server_side(app, tmp_path):
    async with app.router.lifespan_context(app):
        code, _ = await post_run(app, run_input_json("remember me", thread_id="keeper"))
        assert code == 200
    hist = tmp_path / "workspaces" / "keeper" / "history.json"
    assert hist.exists()
    msgs = json.loads(hist.read_bytes())
    assert any(p.get("content") == "remember me"
               for m in msgs for p in m.get("parts", []))


async def test_concurrent_posts_same_thread_both_persisted(app, tmp_path):
    """Phase 4.4 (crit-concurrent-history-clobber): two simultaneous posts to
    ONE thread serialize on a per-thread lock; both user messages survive in
    the final history. RED on v1: both requests loaded the same (empty)
    history and the last save clobbered the first message."""
    import asyncio

    async with app.router.lifespan_context(app):
        (c1, _), (c2, _) = await asyncio.gather(
            post_run(app, run_input_json("first message", thread_id="clobber")),
            post_run(app, run_input_json("second message", thread_id="clobber")),
        )
    assert c1 == 200 and c2 == 200
    hist = tmp_path / "workspaces" / "clobber" / "history.json"
    msgs = json.loads(hist.read_bytes())
    contents = {p.get("content") for m in msgs for p in m.get("parts", [])}
    assert "first message" in contents and "second message" in contents, (
        f"concurrent run clobbered history; surviving user parts: {contents}")


async def test_two_threads_isolated_workspaces(app, tmp_path):
    async with app.router.lifespan_context(app):
        await post_run(app, run_input_json("a", thread_id="iso-a"))
        await post_run(app, run_input_json("b", thread_id="iso-b"))
    ws = tmp_path / "workspaces"
    assert (ws / "iso-a" / "history.json").exists()
    assert (ws / "iso-b" / "history.json").exists()
    a = (ws / "iso-a" / "history.json").read_text()
    assert "iso-b" not in a


async def test_healthz_and_mcp_debug(app):
    import httpx

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            health = (await client.get("/healthz")).json()
            assert health["status"] == "ok"
            assert "harness" in health and "frontend_built" in health  # PLAN Phase 4
            servers = (await client.get("/debug/mcp")).json()
    names = {s["name"] for s in servers}
    assert {"github", "context7", "deepwiki"} <= names
    assert all(s["status"] != "active" for s in servers)  # nothing enabled in tests
