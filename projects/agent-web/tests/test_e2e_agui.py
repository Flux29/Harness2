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
    # Phase 5.1 (crit-history-agent-writable): the authoritative history now
    # lives in the server-only state tree — Matrix D history-LOCATION row
    # flipped here; the message SCHEMA row is unchanged (parity harness).
    async with app.router.lifespan_context(app):
        code, _ = await post_run(app, run_input_json("remember me", thread_id="keeper"))
        assert code == 200
    hist = tmp_path / "state" / "history" / "keeper.json"
    assert hist.exists()
    msgs = json.loads(hist.read_bytes())
    assert any(p.get("content") == "remember me"
               for m in msgs for p in m.get("parts", []))


async def test_agent_workspace_cannot_see_history(app, tmp_path):
    """Phase 5.1 negative test (exit gate 5): after a run, NO copy of history
    exists anywhere under the thread's LocalBackend root — an agent file-tool
    ls/read of the workspace cannot reach it."""
    async with app.router.lifespan_context(app):
        code, _ = await post_run(app, run_input_json("secret run", thread_id="sneaky"))
        assert code == 200
    ws_root = tmp_path / "workspaces"
    assert list(ws_root.rglob("history.json")) == [], (
        "history leaked into an agent-writable workspace")
    assert (tmp_path / "state" / "history" / "sneaky.json").exists()
    # The whole state tree must sit outside every per-thread backend root.
    assert not (tmp_path / "state").resolve().is_relative_to(ws_root.resolve())


async def test_dual_write_window_writes_both_copies(tmp_path):
    """5.1 parallel-run window (HISTORY_DUAL_WRITE=1): both copies written and
    byte-identical; reads stay on the v1 workspace copy (history grows across
    runs), and the divergence ledger stays empty."""
    from dataclasses import replace

    settings = replace(make_settings(tmp_path), history_dual_write=True)
    app = create_app(settings=settings, model=TestModel(call_tools=[]))
    async with app.router.lifespan_context(app):
        await post_run(app, run_input_json("first", thread_id="dw"))
        await post_run(app, run_input_json("second", thread_id="dw"))
    old = tmp_path / "workspaces" / "dw" / "history.json"
    new = tmp_path / "state" / "history" / "dw.json"
    assert old.exists() and new.exists()
    assert old.read_bytes() == new.read_bytes()
    contents = {p.get("content") for m in json.loads(new.read_bytes())
                for p in m.get("parts", [])}
    assert {"first", "second"} <= contents  # run 2 loaded run 1's history
    assert not (tmp_path / "state" / "history" / "_divergences.log").exists()


def test_dual_write_divergence_is_loud(tmp_path, caplog):
    """5.1: if the workspace copy drifts between saves (agent tampering or a
    pipeline bug), the next save logs an ERROR and appends to the ledger the
    live parity run asserts empty."""
    import logging

    from dataclasses import replace

    from agent_web import history

    settings = replace(make_settings(tmp_path), history_dual_write=True)
    history.save(settings, "tamper", [])
    # Simulate agent tampering with the workspace copy between saves.
    history.workspace_path(settings.workspaces_dir, "tamper").write_bytes(b"[]corrupt")
    with caplog.at_level(logging.ERROR, logger="agent_web.history"):
        history.save(settings, "tamper", [])
    assert any("DIVERGENCE" in r.message for r in caplog.records)
    ledger = history.divergence_ledger(settings.state_dir)
    assert ledger.exists() and "tamper" in ledger.read_text()


def test_dual_write_reads_stay_on_v1_copy(tmp_path):
    """5.1: while the window is open the v1 workspace copy is authoritative for
    READS — cutover happens only when the flag is removed."""
    from dataclasses import replace

    from agent_web import history

    on = replace(make_settings(tmp_path), history_dual_write=True)
    off = make_settings(tmp_path)
    history.save(off, "cut", [])  # writes the state copy only
    assert history.load(on, "cut") is None      # window: v1 copy absent -> None
    assert history.load(off, "cut") is not None  # post-cutover: state copy read


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
    hist = tmp_path / "state" / "history" / "clobber.json"
    msgs = json.loads(hist.read_bytes())
    contents = {p.get("content") for m in msgs for p in m.get("parts", [])}
    assert "first message" in contents and "second message" in contents, (
        f"concurrent run clobbered history; surviving user parts: {contents}")


async def test_two_threads_isolated_workspaces(app, tmp_path):
    async with app.router.lifespan_context(app):
        await post_run(app, run_input_json("a", thread_id="iso-a"))
        await post_run(app, run_input_json("b", thread_id="iso-b"))
    assert (tmp_path / "workspaces" / "iso-a").is_dir()
    assert (tmp_path / "workspaces" / "iso-b").is_dir()
    hist = tmp_path / "state" / "history"  # per-thread files since 5.1
    assert (hist / "iso-a.json").exists()
    assert (hist / "iso-b.json").exists()
    a = (hist / "iso-a.json").read_text()
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
    # Phase 4.7: /healthz reports the mount decision actually taken at startup.
    mounted = any(getattr(r, "name", None) == "frontend" for r in app.routes)
    assert health["frontend_mounted"] == ("true" if mounted else "false")
    # Phase 4.7: every row carries the agent's startup snapshot; nothing was
    # ready here, so nothing can claim to be in the agent.
    assert all(s["in_agent"] is False for s in servers)


async def test_debug_mcp_snapshot_matches_agent_toolsets(tmp_path):
    """Phase 4.7 (crit-toolset-frozen): /debug/mcp's in_agent reflects exactly
    the servers whose toolsets were built into the agent at startup — a ready
    server is in, everything else out."""
    import httpx

    (tmp_path / "mcp.json").write_text(json.dumps({"mcpServers": {
        "hosted-http": {"url": "https://example.com/mcp", "type": "http"},
    }}))
    from dataclasses import replace

    settings = replace(make_settings(tmp_path),
                       mcp_config=tmp_path / "mcp.json",
                       mcp_enable=("hosted-http",))
    app = create_app(settings=settings, model=TestModel(call_tools=[]))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            rows = (await client.get("/debug/mcp")).json()
        assert app.state.agent_mcp_servers == ("hosted-http",)
    by_name = {r["name"]: r for r in rows}
    assert by_name["hosted-http"]["in_agent"] is True
    assert all(r["in_agent"] is False
               for n, r in by_name.items() if n != "hosted-http")
