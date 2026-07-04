"""Parity Matrix A — Settings (agent-web), field by field.

The disposition column of Matrix A lives here as executable assertions. Rows
marked 'identical' assert against the committed baseline; rows a step flips are
edited here in that step's commit with the citation.
"""
from __future__ import annotations

import dataclasses


def _asdict(s):
    return {f.name: (list(v) if isinstance(v := getattr(s, f.name), tuple) else str(v)
                     if f.name in ("workspaces_dir", "mcp_config") else v)
            for f in dataclasses.fields(s)}


def test_settings_field_set_is_stable(code_default_settings, baseline):
    """The set of Settings fields is a contract (additive-only)."""
    got = set(_asdict(code_default_settings).keys())
    expected = set(baseline("schemas-v1/settings.json").keys())
    missing = expected - got
    assert not missing, f"Matrix A: Settings dropped fields {missing}"


def test_settings_code_defaults_match_baseline(code_default_settings, baseline):
    b = baseline("schemas-v1/settings.json")
    got = _asdict(code_default_settings)

    # --- Row: model. FLIPS in step 3.4 to openrouter:z-ai/glm-5.2. Until then,
    # identical to the v1 baseline (openrouter:z-ai/glm-4.6). ---
    assert got["model"] == b["model"], "Matrix A[model]: unexpected model default (flip belongs to step 3.4)"

    # --- Rows that are identical throughout Phases 0-3 ---
    for row in ("fallback_model", "workspaces_dir", "mcp_config", "mcp_enable",
                "cors_origins", "cost_budget_usd", "skills_dir"):
        assert got[row] == b[row], f"Matrix A[{row}]: drifted from v1 baseline"

    # --- Flag rows. Truthiness RULE changes in 3.3, but the resolved default
    # values for a code-default (neutralized) env stay: web_tools/tracing on,
    # the deferred flags off. Semantic parity is enforced in the 3.3 flag table
    # test; here we assert the resolved defaults are unchanged. ---
    assert got["web_tools"] is True
    assert got["tracing"] is True
    for flag in ("teams", "liteparse", "execute", "browser", "tool_search", "improve"):
        assert got[flag] is False, f"Matrix A[{flag}]: code default must be off"
