"""Environment-driven settings. Every knob is an env var; no config framework."""
from __future__ import annotations

import os
from dataclasses import dataclass
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


_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # projects/agent-web


def _mcp_config_path() -> Path:
    """Resolve MCP_CONFIG CWD-independently (Phase 4.7, disc-mcp-config-cwd-
    relative). A relative path — including the default ``mcp.json`` — anchors
    to the project root (where the deployed mcp.json lives), so which MCP
    servers register no longer depends on the process CWD. Under the deployed
    launch (CWD = projects/agent-web) this resolves to the same file as
    before; launched from anywhere else it now finds that file instead of
    silently dropping mcp.json's servers. Absolute paths are taken as-is."""
    p = Path(os.getenv("MCP_CONFIG", "mcp.json"))
    return p if p.is_absolute() else _PROJECT_ROOT / p


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("AGENT_MODEL", "openrouter:z-ai/glm-5.2")
    # Auto-retry on another model if the primary errors (rate limits, outages).
    fallback_model: str | None = os.getenv("FALLBACK_MODEL") or None
    workspaces_dir: Path = Path(os.getenv("WORKSPACES_DIR", "workspaces"))
    # Phase 5.1 (crit-history-agent-writable): server-only state tree, a
    # SIBLING of workspaces_dir — never inside any LocalBackend root, so agent
    # file tools cannot read or rewrite what lives here (history, and 6.3's
    # checkpoint store if ADR 6.3 chooses durability).
    state_dir: Path = Path(os.getenv("STATE_DIR", "state"))
    # Migration window (5.1 parallel-run, NOT a hard cutover): 1 = also write
    # the v1 workspace history copy and diff the pair on every save; READS stay
    # on the v1 copy while the window is open. Cut over (remove the flag) after
    # N=5 clean sessions (empty state/history/_divergences.log). The matching
    # Gate 4 dup-allowlist entry's expiry is this window's hard deadline.
    history_dual_write: bool = _flag("HISTORY_DUAL_WRITE", False)
    mcp_config: Path = _mcp_config_path()
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
    # --- Composed security posture (ADR-0020). The /agent request-authenticity
    # guard closes the verified cross-origin drive-by; see app._authorize.
    # Optional bearer: unset by default (loopback + guard is the single-user
    # baseline); REQUIRED whenever the service binds beyond loopback.
    agent_token: str | None = os.getenv("AGENT_TOKEN") or None
    # Reject non-loopback Host headers (DNS-rebinding defense). On by default;
    # tests over synthetic ASGI hosts (Host: testserver) set it False.
    require_loopback_host: bool = _flag("REQUIRE_LOOPBACK_HOST", True)
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
    # Phase 5.2 (crit-fork-exec-gate): Live Run Forking runs LLM-generated code
    # AND its pytest suite ON THE HOST (LocalBackend, no interrupt hook in the
    # harness for test_command). v1 had it always-on while shell execute was
    # approval-gated — that asymmetry was the defect. Now env-gated like its
    # siblings: FORKING=1 opts in, documented next to the browser warning.
    forking: bool = _flag("FORKING", False)
    # /improve: analyzes past sessions, proposes updates to MEMORY.md/SOUL.md/AGENTS.md
    improve: bool = _flag("IMPROVE", False)
    # --- Fork configuration (ADR-0011), centralized here (Phase 3.5). Defaults
    # preserve the previous hardcoded behavior. Whether forking stays always-on is
    # a Phase 5.2 decision; this step only gathers the knobs into one place.
    fork_test_command: str = os.getenv("FORK_TEST_COMMAND", "pytest -q")
    fork_max_branches: int = int(os.getenv("FORK_MAX_BRANCHES", "4"))
    fork_test_timeout_s: float = float(os.getenv("FORK_TEST_TIMEOUT_S", "60"))
    # Conservative budgets so a runaway branch can't repeat the 22-min/48-call
    # burn (ADR-0011). Applied per-branch / aggregate when a fork is invoked.
    fork_branch_budget_usd: float = float(os.getenv("FORK_BRANCH_BUDGET_USD", "0.75"))
    fork_aggregate_budget_usd: float = float(os.getenv("FORK_AGGREGATE_BUDGET_USD", "2.5"))
