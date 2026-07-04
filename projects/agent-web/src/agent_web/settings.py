"""Environment-driven settings. Every knob is an env var; no config framework."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _flag(name: str, default: bool) -> bool:
    """Unified env-flag parsing (Phase 3.3).

    Case-insensitive, one truthy/falsy set for every flag. Empty string and
    unset both mean "use the default"; an unknown value also falls back to the
    default — so `EXECUTE=False` resolves to OFF, never ON (the v1 case-
    sensitivity bug). Semantic parity with v1: every v1-valid value resolves
    identically except the documented fix (`False`/`FALSE` -> off).
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v == "":
        return default
    if v in _TRUTHY:
        return True
    if v in _FALSY:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("AGENT_MODEL", "openrouter:z-ai/glm-5.2")
    # Auto-retry on another model if the primary errors (rate limits, outages).
    fallback_model: str | None = os.getenv("FALLBACK_MODEL") or None
    workspaces_dir: Path = Path(os.getenv("WORKSPACES_DIR", "workspaces"))
    mcp_config: Path = Path(os.getenv("MCP_CONFIG", "mcp.json"))
    # Comma-separated server names to enable (builtins and/or mcp.json entries).
    # 3.4a decision: the CODE default stays secret-free (context7,deepwiki). The
    # deployed roster (context7,deepwiki,github,logfire) needs a PAT + read token,
    # so it lives in .env, not here — a default that fails without secrets is worse.
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
    web_tools: bool = _flag("WEB_TOOLS", True)
    # Logfire tracing (needs LOGFIRE_TOKEN too); TRACING=0 disables explicitly.
    tracing: bool = _flag("TRACING", True)
    # --- Deferred features (ADR-0015 ledger), all OFF by default. Flip via .env.
    teams: bool = _flag("TEAMS", False)                 # agent teams: shared todos + message bus
    liteparse: bool = _flag("LITEPARSE", False)         # PDF/DOCX/XLSX parsing (Node >= 18 + extra)
    execute: bool = _flag("EXECUTE", False)             # shell execute tool, approval-gated (Docker extra advised)
    browser: bool = _flag("BROWSER_AUTOMATION", False)  # Playwright browser automation (extra + browsers)
    # search-on-demand tool schemas instead of flat lists (token saver as MCP roster grows)
    tool_search: bool = _flag("TOOL_SEARCH", False)
    # /improve: analyzes past sessions, proposes updates to MEMORY.md/SOUL.md/AGENTS.md
    improve: bool = _flag("IMPROVE", False)
