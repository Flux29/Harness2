"""App factory — the whole web layer we own (ADR-0012).

POST /agent    AG-UI run endpoint (SSE stream out)
GET  /healthz  liveness
GET  /debug/mcp  registry status: answers "why is this tool missing"
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path as _Path
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import Response
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.ag_ui import AGUIAdapter

from . import history, observability
from .agent import build_agent
from .deps import make_deps
from .mcp import build_registry, build_toolsets, status
from .settings import Settings


def create_app(
    settings: Settings | None = None,
    model: Any | None = None,
    extra_tools: tuple[Any, ...] = (),
) -> FastAPI:
    settings = settings or Settings()
    if settings.tracing:
        observability.configure()  # still a no-op without LOGFIRE_TOKEN

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        registry = build_registry(settings.mcp_config, settings.mcp_enable)
        app.state.registry = registry
        toolsets, mcp_snapshot = build_toolsets(registry)
        # Phase 4.7 (crit-toolset-frozen): the agent's toolsets are built once,
        # here; record exactly which servers made it in so /debug/mcp can
        # report the snapshot alongside live registry status.
        app.state.agent_mcp_servers = mcp_snapshot
        app.state.agent = build_agent(
            settings, model=model, mcp_toolsets=toolsets,
            extra_tools=extra_tools,
        )
        yield

    app = FastAPI(title="agent-web", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins),
        allow_methods=["*"], allow_headers=["*"],
    )

    # Phase 4.4 (crit-concurrent-history-clobber): one in-process lock per
    # thread id serializes the whole load->run->save window. Concurrent posts
    # to one thread queue; distinct threads are unaffected. In-process only —
    # matches the single-server deployment (ADR-0012).
    thread_locks: dict[str, asyncio.Lock] = {}

    def _thread_lock(thread_id: str) -> asyncio.Lock:
        return thread_locks.setdefault(thread_id, asyncio.Lock())

    @app.post("/agent")
    async def run_agent(request: Request) -> Response:
        accept = request.headers.get("accept", SSE_CONTENT_TYPE)
        try:
            run_input = AGUIAdapter.build_run_input(await request.body())
        except ValidationError as e:
            # e.json() already returns a JSON string (the error list). Wrapping it
            # in json.dumps() double-encoded it into a JSON string literal, so
            # json.loads(body) yielded a str, not the error object (Phase 3.2).
            return Response(content=e.json(), media_type="application/json",
                            status_code=HTTPStatus.UNPROCESSABLE_ENTITY)

        thread_id = run_input.thread_id

        async def on_complete(result: Any) -> None:
            history.save(settings, thread_id, result.all_messages())

        adapter = AGUIAdapter(agent=request.app.state.agent, run_input=run_input, accept=accept)

        async def locked_events():
            # history.load moved INSIDE the lock: a queued request must see the
            # previous run's saved history, not a pre-lock snapshot.
            async with _thread_lock(thread_id):
                stream = adapter.run_stream(
                    deps=make_deps(settings.workspaces_dir, thread_id),
                    message_history=history.load(settings, thread_id),
                    on_complete=on_complete,
                )
                async for event in stream:
                    yield event

        return adapter.streaming_response(locked_events())

    # The static mount is decided ONCE, here at app creation; healthz reports
    # this decision (frontend_mounted) next to the live on-disk state
    # (frontend_built) so the two can't silently contradict (Phase 4.7: a dist
    # built after startup is visible as built=<time> + mounted=false).
    startup_dist = _frontend_dist()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        import pydantic_deep

        dist = _frontend_dist()
        built = (
            datetime.fromtimestamp(dist.joinpath("index.html").stat().st_mtime, timezone.utc).isoformat()
            if dist and dist.joinpath("index.html").exists() else "not built (dev mode?)"
        )
        return {
            "status": "ok",
            "harness": getattr(pydantic_deep, "__version__", "?"),
            "frontend_built": built,
            "frontend_mounted": "true" if startup_dist else "false",
        }

    @app.get("/debug/mcp")
    async def debug_mcp() -> list[dict[str, Any]]:
        # Phase 4.7 (crit-toolset-frozen): live registry status PLUS the
        # agent's startup snapshot. A server that turns ready after startup
        # shows status=ready, in_agent=false — honest, not silently diverging.
        snapshot = set(getattr(app.state, "agent_mcp_servers", ()))
        rows = status(app.state.registry)
        for row in rows:
            row["in_agent"] = row["name"] in snapshot
        return rows

    if startup_dist:
        from starlette.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(startup_dist), html=True), name="frontend")

    return app



def _frontend_dist() -> _Path | None:
    """Locate the built frontend (frontend/dist); env-overridable, None if absent."""
    import os

    p = _Path(os.getenv("FRONTEND_DIST", str(_Path(__file__).parents[2] / "frontend" / "dist")))
    return p if (p / "index.html").exists() else None
