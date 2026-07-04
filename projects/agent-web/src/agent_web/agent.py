"""The single agent definition (ADR-0015): full harness feature set, one call.

create_deep_agent returns a plain pydantic_ai.Agent, so the AG-UI adapter uses
it directly. output_type includes DeferredToolRequests (ADR-0012 risk 1 —
resolved: it's a supported first-class parameter) so requires_approval tools
pause into AG-UI interrupts instead of erroring.
"""
from __future__ import annotations

from typing import Any, Sequence

from pydantic_ai.tools import DeferredToolRequests
from pydantic_deep import LiveForkCapability, create_deep_agent

from .settings import Settings


def build_agent(
    settings: Settings,
    model: Any | None = None,
    mcp_toolsets: Sequence[Any] = (),
    extra_tools: Sequence[Any] = (),
):
    return create_deep_agent(
        instructions=(
            "Tool selection rules: 1) Your full toolbox is LARGER than the tools "
            "you can currently see — when a task involves an external service "
            "(GitHub, library docs, telemetry/Logfire, databases), FIRST call "
            "search_tools with relevant keywords to discover the right tools. "
            "2) Prefer MCP tools (github_*, context7_*, logfire_*) over shell or "
            "browser for anything they cover — GitHub repos/issues/PRs MUST use "
            "github_* tools, never `gh`, `winget`, or browsing github.com. "
            "3) NEVER navigate to login pages or enter credentials into any "
            "website; your credentials are provided via tools, not web forms. "
            "4) Do not install software unless the user explicitly asks. "
            "5) If a needed tool seems missing after searching, say so and stop "
            "instead of improvising around it."
        ),
        model=model if model is not None else settings.model,
        fallback_model=settings.fallback_model if model is None else None,
        output_type=[str, DeferredToolRequests],
        tools=list(extra_tools) or None,
        mcp_servers=list(mcp_toolsets) or None,
        # Opt-ins per ADR-0015 (defaults already cover todo/fs/subagents/skills/
        # memory/monitoring/context/eviction/history-archive/cost/stuck-loop):
        forking=LiveForkCapability(test_command="pytest -q", max_branches=4),
        include_checkpoints=True,
        skill_directories=[settings.skills_dir] if settings.skills_dir else None,
        cost_budget_usd=settings.cost_budget_usd,
        web_search=settings.web_tools,
        web_fetch=settings.web_tools,
        # Env-gated deferred features (ADR-0015): all off unless flipped in .env.
        include_teams=settings.teams,
        include_improve=settings.improve,
        include_liteparse=settings.liteparse,
        tool_search=settings.tool_search,
        include_execute=True if settings.execute else None,
        interrupt_on={"execute": True} if settings.execute else None,
        capabilities=_capabilities(settings),
    )


def _capabilities(settings: Settings) -> list[Any] | None:
    if not settings.browser:
        return None
    from pydantic_deep import BrowserCapability  # requires the 'browser' extra

    return [BrowserCapability()]
