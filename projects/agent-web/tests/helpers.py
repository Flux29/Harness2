"""Shared E2E helpers: real AG-UI wire types, ASGI-transport client."""
from __future__ import annotations

import uuid
from typing import Any

from ag_ui.core import RunAgentInput, UserMessage

from agent_web.settings import Settings


def make_settings(tmp_path) -> Settings:
    return Settings(
        workspaces_dir=tmp_path / "workspaces",
        state_dir=tmp_path / "state",
        history_dual_write=False,  # post-cutover default; window tested explicitly
        mcp_config=tmp_path / "absent-mcp.json",
        mcp_enable=(),  # no network in tests
        web_tools=False,  # TestModel rejects built-in tools
        tracing=False,  # never export traces from tests
        # Pin ALL feature flags: ambient env must never shape a test
        # (BROWSER is a standard OS env var and burned us once already).
        teams=False, liteparse=False, execute=False, browser=False, tool_search=False, improve=False,
    )


def run_input_json(prompt: str, thread_id: str | None = None, **overrides: Any) -> str:
    payload = RunAgentInput(
        thread_id=thread_id or f"t-{uuid.uuid4().hex[:8]}",
        run_id=f"r-{uuid.uuid4().hex[:8]}",
        messages=[UserMessage(id=f"m-{uuid.uuid4().hex[:8]}", role="user", content=prompt)],
        tools=[], context=[], state={}, forwarded_props={},
        **overrides,
    )
    return payload.model_dump_json(by_alias=True)


async def post_run(app, body: str) -> tuple[int, str]:
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with client.stream(
            "POST", "/agent", content=body,
            headers={"content-type": "application/json"}, timeout=60,
        ) as r:
            text = "".join([chunk async for chunk in r.aiter_text()])
            return r.status_code, text
