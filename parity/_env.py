"""Shared neutralization for capturing/checking CODE defaults.

The local deployment `.env` sets the deferred flags on and MCP_ENABLE to the
deployed roster. Matrix A is about the *code* defaults in settings.py, so both
the baseline capture and the parity test must neutralize the `.env` to the code
defaults. Keeping this map in one place stops the two from drifting.

Only the fields the deployment `.env` overrides need pinning here; fields the
`.env` leaves alone (AGENT_MODEL, WORKSPACES_DIR, ...) fall through to the code
default and must NOT be listed, so a real change to a code default is still
caught.
"""
from __future__ import annotations

# env var -> value that reproduces the settings.py code default
CODE_DEFAULT_ENV: dict[str, str] = {
    "MCP_ENABLE": "context7,deepwiki",
    "WEB_TOOLS": "1",
    "TRACING": "1",
    "TEAMS": "0",
    "LITEPARSE": "0",
    "EXECUTE": "0",
    "BROWSER_AUTOMATION": "0",
    "TOOL_SEARCH": "0",
    "IMPROVE": "0",
}
