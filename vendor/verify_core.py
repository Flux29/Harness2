"""Core smoke test for the vendored pydantic-deepagents harness.

Run from any consumer venv that installed the vendored package, e.g. (Windows):
    cd <workspace-root>\\projects\\agent-web
    uv venv
    uv pip install -e "..\\..\\vendor\\pydantic-deepagents[web,mcp,yaml]" "pydantic-ai-slim[ag-ui]"
    uv run python ..\\..\\vendor\\verify_core.py

Exit code 0 = core is healthy. Network is never contacted.
This is the single gate for BOTH consumers (eval-optimizer, agent-web) after any
re-vendor — run it from each venv. See also revendor_check.py (tree integrity).
"""
from __future__ import annotations
import inspect, sys

def ok(msg): print(f"[ OK ] {msg}")
def info(msg): print(f"[info] {msg}")
def fail(msg): print(f"[FAIL] {msg}")

def main() -> int:
    print(f"python: {sys.version.split()[0]}")
    import pydantic_deep as pd
    print(f"pydantic_deep: {getattr(pd, '__version__', 'n/a')}")

    from pydantic_deep import (
        create_deep_agent, LiveForkCapability, BranchSpec, BranchIsolation,
        ForkCoordinator, DeepAgentDeps, InMemoryCheckpointStore,
    )
    ok("core imports")

    # Vendor patch: public per-branch outcome accessor (Option A seed).
    fn = getattr(ForkCoordinator, "branch_outcomes", None)
    if fn is None or not inspect.iscoroutinefunction(fn):
        fail("ForkCoordinator.branch_outcomes missing/not-async — vendor patch not applied")
        return 1
    ok("vendor patch present: ForkCoordinator.branch_outcomes (async)")

    # Build an agent with forking wired, using a test model (no network).
    from pydantic_ai.models.test import TestModel
    agent = create_deep_agent(
        model=TestModel(),
        forking=LiveForkCapability(test_command="pytest -q", max_branches=4),
        include_checkpoints=True,
        web_search=False, web_fetch=False, include_subagents=False,
    )
    ok(f"create_deep_agent + forking builds -> {type(agent).__name__}")

    # OpenRouter model object (needs the 'openai' extra; OpenRouter is OpenAI-compatible).
    try:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        m = OpenAIChatModel("z-ai/glm-4.6", provider=OpenAIProvider(
            base_url="https://openrouter.ai/api/v1", api_key="dummy-not-used"))
        ok(f"OpenRouter model object -> {m.model_name}")
    except ImportError:
        info("OpenRouter path skipped: install the 'openai' extra "
             "(uv pip install -e \".[openai]\") — or the 'cli' extra bundles it.")

    # Full-default agent (only works if web-search deps present).
    try:
        create_deep_agent(model=TestModel())
        ok("full-default create_deep_agent builds (duckduckgo deps present)")
    except Exception as e:
        info(f"default web_search disabled here: {type(e).__name__}. "
             "Install 'duckduckgo'/ddgs or pass web_search=False in code.")

    # --- AG-UI surface (ADR-0012): pydantic-ai side, not a vendor extra. ---
    try:
        from pydantic_ai.ui.ag_ui import AGUIAdapter  # noqa: F401
        from pydantic_ai.ui import SSE_CONTENT_TYPE  # noqa: F401
        ok("AG-UI adapter importable (pydantic-ai-slim[ag-ui])")
    except ImportError:
        info("AG-UI skipped: pip install 'pydantic-ai-slim[ag-ui]' (required for agent-web)")

    # --- MCP subsystem (ADR-0014): vendored registry + config parsing. ---
    try:
        from pydantic_deep.mcp import (  # noqa: F401
            MCPRegistry, MCPServerConfig, parse_mcp_servers, builtin_mcp_servers,
        )
        fixture = {
            "local-stdio": {"command": "npx", "args": ["-y", "some-mcp"], "env": {"K": "${K}"}},
            "hosted-http": {"url": "https://example.com/mcp", "type": "http"},
        }
        parsed = parse_mcp_servers(fixture)
        assert len(parsed) == 2 and {c.transport for c in parsed} == {"stdio", "http"}, parsed
        names = {c.name for c in builtin_mcp_servers()}
        assert {"github", "context7", "deepwiki"} <= names, names
        ok(f"MCP registry live: parse_mcp_servers fixture -> 2 configs; builtins {sorted(names)}")
    except ImportError:
        info("MCP skipped: install the vendor 'mcp' extra (…[web,mcp,yaml]) — required for agent-web")

    print("\nCORE OK — harness imports, forking wires, vendor patch live.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
