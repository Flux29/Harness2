"""App factory — the whole web layer we own (ADR-0012).

POST /agent    AG-UI run endpoint (SSE stream out)
GET  /healthz  liveness
GET  /debug/mcp  registry status: answers "why is this tool missing"
"""
from __future__ import annotations

import asyncio
import json
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

from . import history, observability, threads
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
    # ADR-0020: CORS narrowed from "*" to what the AG-UI client actually uses,
    # so the allowlist is a real boundary (paired with the /agent guard, which
    # forces cross-origin writes through preflight).
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type", "authorization", "accept"],
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
        # ADR-0020: request-authenticity guard, BEFORE any run/history/model
        # work. Closes the verified cross-origin drive-by (a browser
        # text/plain "simple request" reaching the endpoint without preflight).
        reason = _authorize(request, settings)
        if reason is not None:
            return Response(content=json.dumps({"error": reason}),
                            media_type="application/json",
                            status_code=HTTPStatus.FORBIDDEN)

        accept = request.headers.get("accept", SSE_CONTENT_TYPE)
        try:
            run_input = AGUIAdapter.build_run_input(await request.body())
        except ValidationError as e:
            # e.json() already returns a JSON string (the error list). Wrapping it
            # in json.dumps() double-encoded it into a JSON string literal, so
            # json.loads(body) yielded a str, not the error object (Phase 3.2).
            try:
                body = e.json()
            except ValueError:
                # e.json() re-embeds the request's input bytes; invalid UTF-8 in
                # them crashes the serializer itself → raw 500 (gate-6 live find,
                # disc-422-serialization-crash). The error list is the contract,
                # not the offending bytes — drop the input and serialize safely.
                body = json.dumps(
                    e.errors(include_url=False, include_input=False), default=str
                )
            return Response(content=body, media_type="application/json",
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
                    deps=make_deps(settings.workspaces_dir, settings.state_dir, thread_id),
                    message_history=history.load(settings, thread_id),
                    on_complete=on_complete,
                )
                async for event in stream:
                    yield event

        return adapter.streaming_response(locked_events())

    # --- Thread persistence endpoints (feat-thread-persistence, ISSUE-4) ---
    # Same ADR-0020 trust surface as /agent minus the content-type rule (GETs
    # carry no body; that rule exists to force preflight on cross-origin
    # WRITES). Matrix D: additive-only — no existing endpoint changes shape.

    def _refuse(reason: str, code: HTTPStatus = HTTPStatus.FORBIDDEN) -> Response:
        return Response(content=json.dumps({"error": reason}),
                        media_type="application/json", status_code=code)

    @app.get("/threads")
    async def get_threads(request: Request) -> Response:
        reason = _authorize(request, settings, require_json=False)
        if reason is not None:
            return _refuse(reason)
        # active_runs is wired by the run-survival layer; empty set until then.
        running = frozenset(getattr(app.state, "active_runs", {}) or ())
        return Response(
            content=json.dumps({"threads": threads.list_threads(settings, running)}),
            media_type="application/json",
        )

    @app.get("/threads/{thread_id}/messages")
    async def get_thread_messages(thread_id: str, request: Request) -> Response:
        reason = _authorize(request, settings, require_json=False)
        if reason is not None:
            return _refuse(reason)
        payload = threads.thread_payload(settings, thread_id)
        if payload is None:
            return _refuse("unknown thread", HTTPStatus.NOT_FOUND)
        return Response(content=json.dumps(payload), media_type="application/json")

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



_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _loopback_host(host: str) -> bool:
    """True if a Host header names a loopback interface (port stripped)."""
    if not host:
        return False
    h = host.strip()
    if h.startswith("["):                       # [::1]:8801
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:                      # 127.0.0.1:8801
        h = h.rsplit(":", 1)[0]
    return h in _LOOPBACK_HOSTS


def _authorize(request: Request, settings: Settings, *, require_json: bool = True) -> str | None:
    """ADR-0020 request-authenticity checks. Returns a reason string when the
    request must be REFUSED (403), else None. Ordered so the single verified
    drive-by (text/plain simple request) is caught by the content-type rule
    even with every other check disabled.

    - Bearer: when AGENT_TOKEN is set, require it (the bind-beyond-loopback and
      future multi-user control).
    - Content-Type must be application/json (``require_json=True``, the POST
      /agent posture): removes the CORS "simple request" bypass, so a
      cross-origin write now needs a preflight the allowlist answers. The
      body-less GET endpoints pass ``require_json=False`` — the rule exists to
      gate writes, and GETs send no content-type; every other check still
      applies (ADR-0023).
    - Origin, when present: same-origin (matches Host) or in cors_origins.
    - Host must be loopback (when require_loopback_host): defeats DNS rebinding,
      where Origin and Host both carry the attacker's rebound domain.
    """
    if settings.agent_token:
        if request.headers.get("authorization", "") != f"Bearer {settings.agent_token}":
            return "missing or invalid bearer token"

    if require_json:
        ctype = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            return "content-type must be application/json"

    origin = request.headers.get("origin")
    if origin is not None:
        host = request.headers.get("host", "")
        same_origin = origin.split("://", 1)[-1] == host
        if not same_origin and origin not in settings.cors_origins:
            return "origin not allowed"

    if settings.require_loopback_host and not _loopback_host(request.headers.get("host", "")):
        return "host is not loopback"

    return None


def _frontend_dist() -> _Path | None:
    """Locate the built frontend (frontend/dist); env-overridable, None if absent."""
    import os

    p = _Path(os.getenv("FRONTEND_DIST", str(_Path(__file__).parents[2] / "frontend" / "dist")))
    return p if (p / "index.html").exists() else None
