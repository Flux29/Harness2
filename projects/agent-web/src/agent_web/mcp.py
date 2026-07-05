"""MCP wiring — everything through the harness-native registry (ADR-0014)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic_deep.mcp import MCPRegistry, builtin_mcp_servers, parse_mcp_servers

log = logging.getLogger("agent_web.mcp")


def build_registry(mcp_config: Path, enable: tuple[str, ...]) -> MCPRegistry:
    configs = list(builtin_mcp_servers())
    if mcp_config.exists():
        data = json.loads(mcp_config.read_text())
        configs += parse_mcp_servers(data.get("mcpServers", {}), enabled=False)
    registry = MCPRegistry(configs)
    for name in enable:
        if not registry.set_enabled(name, True):
            log.warning("MCP_ENABLE names unknown server %r — ignored", name)
    return registry


def build_toolsets(registry: MCPRegistry) -> tuple[list[Any], tuple[str, ...]]:
    """Build ready servers, each namespaced then made resilient.

    PrefixedToolset renames every tool to `<server>_<tool>` — without it, MCP
    tools collide with harness tools (e.g. github's `delete_file` vs the
    forking toolset's) and pydantic-ai refuses to start the run.

    Returns ``(toolsets, names)``: names are the servers actually built into
    the agent — the startup snapshot that /debug/mcp reports next to live
    registry status (Phase 4.7, crit-toolset-frozen), so the one readiness
    decision has one owner and the two views cannot silently disagree.
    """
    from pydantic_ai.toolsets import PrefixedToolset
    from pydantic_deep.mcp import make_resilient

    def on_degraded(name: str, reason: str) -> None:
        log.warning("MCP server %r degraded: %s", name, reason)

    out: list[Any] = []
    names: list[str] = []
    for config in registry.list_servers():
        if registry.status(config) != "ready":
            continue
        toolset = PrefixedToolset(registry.build(config), config.name.replace("-", "_"))
        out.append(make_resilient(toolset, config.name, on_degraded))
        names.append(config.name)
    return out, tuple(names)


def status(registry: MCPRegistry) -> list[dict[str, Any]]:
    return [
        {"name": c.name, "transport": c.transport, "enabled": c.enabled,
         "builtin": c.builtin, "status": registry.status(c)}
        for c in registry.list_servers()
    ]
