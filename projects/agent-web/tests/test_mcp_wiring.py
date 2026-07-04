"""MCP toolsets must be name-spaced (github's delete_file collided with the
harness's own — pydantic-ai aborts runs on duplicate tool names)."""
from __future__ import annotations

from pydantic_deep.mcp import MCPRegistry, parse_mcp_servers

from agent_web.mcp import build_toolsets


def test_toolsets_are_prefixed_and_resilient():
    registry = MCPRegistry(parse_mcp_servers(
        {"hosted-http": {"url": "https://example.com/mcp", "type": "http"}}, enabled=True,
    ))
    toolsets = build_toolsets(registry)
    assert len(toolsets) == 1
    resilient = toolsets[0]
    inner = getattr(resilient, "wrapped", None)
    assert type(inner).__name__ == "PrefixedToolset", type(inner)
    assert getattr(inner, "prefix", None) == "hosted_http"
