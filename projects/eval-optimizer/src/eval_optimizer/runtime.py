"""Run helpers.

429 / 5xx / network retries (honoring Retry-After) now live at the HTTP transport
layer — see `models._retrying_http_client` (ADR-0008). So `agent_run` is just a
thin convenience wrapper; `gather_limited` caps how many agents run at once.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Sequence


async def agent_run(agent: Any, prompt: str, *, deps: Any = None, label: str = "", **_ignored: Any) -> Any:
    """Run ``agent.run(prompt, deps=deps)``. Transport-level retry handles 429s.

    `label`/extra kwargs are accepted for call-site compatibility and ignored.
    """
    if deps is not None:
        return await agent.run(prompt, deps=deps)
    return await agent.run(prompt)


async def gather_limited(
    factories: Sequence[Callable[[], Awaitable[Any]]],
    *,
    limit: int = 1,
) -> list[Any]:
    """Run coroutine factories with at most ``limit`` in flight at once.

    Pass factories (callables returning a coroutine), not coroutines, so nothing
    starts before its turn.
    """
    sem = asyncio.Semaphore(limit)

    async def _run(factory: Callable[[], Awaitable[Any]]) -> Any:
        async with sem:
            return await factory()

    return await asyncio.gather(*(_run(f) for f in factories))
