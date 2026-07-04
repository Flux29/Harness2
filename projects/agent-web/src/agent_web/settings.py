"""Environment-driven settings. Every knob is an env var; no config framework."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("AGENT_MODEL", "openrouter:z-ai/glm-4.6")
    # Auto-retry on another model if the primary errors (rate limits, outages).
    fallback_model: str | None = os.getenv("FALLBACK_MODEL") or None
    workspaces_dir: Path = Path(os.getenv("WORKSPACES_DIR", "workspaces"))
    mcp_config: Path = Path(os.getenv("MCP_CONFIG", "mcp.json"))
    # Comma-separated server names to enable (builtins and/or mcp.json entries).
    mcp_enable: tuple[str, ...] = tuple(
        s.strip() for s in os.getenv("MCP_ENABLE", "context7,deepwiki").split(",") if s.strip()
    )
    cors_origins: tuple[str, ...] = tuple(
        s.strip() for s in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if s.strip()
    )
    cost_budget_usd: float | None = (
        float(os.environ["COST_BUDGET_USD"]) if os.getenv("COST_BUDGET_USD") else None
    )
    skills_dir: str | None = os.getenv("SKILLS_DIR") or None
    # web_search/web_fetch are pydantic-ai BUILT-IN tools: real providers support
    # them, TestModel does not. Off in tests via make_settings(web_tools=False).
    web_tools: bool = os.getenv("WEB_TOOLS", "1") not in ("0", "false", "no")
    # Logfire tracing (needs LOGFIRE_TOKEN too); TRACING=0 disables explicitly.
    tracing: bool = os.getenv("TRACING", "1") not in ("0", "false", "no")
    # --- Deferred features (ADR-0015 ledger), all OFF by default. Flip via .env.
    teams: bool = os.getenv("TEAMS", "0") not in ("0", "false", "no", "")          # agent teams: shared todos + message bus
    liteparse: bool = os.getenv("LITEPARSE", "0") not in ("0", "false", "no", "")  # PDF/DOCX/XLSX parsing (Node >= 18 + extra)
    execute: bool = os.getenv("EXECUTE", "0") not in ("0", "false", "no", "")      # shell execute tool, approval-gated (Docker extra advised)
    browser: bool = os.getenv("BROWSER_AUTOMATION", "0") not in ("0", "false", "no", "")      # Playwright browser automation (extra + browsers)
    tool_search: bool = os.getenv("TOOL_SEARCH", "0") not in ("0", "false", "no", "")
    # /improve: analyzes past sessions, proposes updates to MEMORY.md/SOUL.md/AGENTS.md
    improve: bool = os.getenv("IMPROVE", "0") not in ("0", "false", "no", "")  # search-on-demand tools instead of flat schemas
