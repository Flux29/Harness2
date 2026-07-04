#!/usr/bin/env python
"""Capture the OFFLINE v1 baselines (Phase 0.2, the CI-checkable subset).

Live baselines (SSE transcripts, Logfire traces — Matrices C-wire and E) are
captured separately in the local gate sessions with real secrets; see
baseline/sse-v1/README.md and baseline/traces-v1/README.md.

This script is deterministic and side-effect free beyond writing under baseline/.
Run it with a SANITIZED environment (see capture_baseline_clean.sh) so Settings
reflects code defaults, not the local machine's .env.

  agent-web scope:  uv run --project projects/agent-web python parity/capture_baseline.py aw
  eval-opt scope:   uv run --project projects/eval-optimizer python parity/capture_baseline.py eo
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import CODE_DEFAULT_ENV  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "baseline"


def _write(rel: str, obj) -> None:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("wrote", p.relative_to(ROOT))


def capture_agent_web() -> None:
    # Neutralize the deployment .env to the code defaults before importing
    # settings (load_dotenv is override=False, so these win). Kept in sync with
    # the parity test via parity/_env.py.
    os.environ.update(CODE_DEFAULT_ENV)

    from fastapi.testclient import TestClient
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from pydantic_ai.models.test import TestModel

    from agent_web.app import create_app
    from agent_web.settings import Settings
    from agent_web.deps import thread_slug

    # ---- Matrix A: Settings field-by-field (code defaults) ----
    s = Settings()
    settings_dict = {f.name: getattr(s, f.name) for f in dataclasses.fields(s)}
    _write("schemas-v1/settings.json", settings_dict)

    # v1 truthiness rules, captured as the semantic spec Matrix A enforces.
    _write("schemas-v1/settings-flag-rules.json", {
        "note": "v1 per-flag empty-string and case semantics (Matrix A). Phase 3.3 unifies these.",
        "web_tools": {"env": "WEB_TOOLS", "default_on": True, "empty_string": "on", "falsy": ["0", "false", "no"]},
        "tracing": {"env": "TRACING", "default_on": True, "empty_string": "on", "falsy": ["0", "false", "no"]},
        "teams": {"env": "TEAMS", "default_on": False, "empty_string": "off", "falsy": ["0", "false", "no", ""], "case_sensitive": True},
        "liteparse": {"env": "LITEPARSE", "default_on": False, "empty_string": "off", "falsy": ["0", "false", "no", ""], "case_sensitive": True},
        "execute": {"env": "EXECUTE", "default_on": False, "empty_string": "off", "falsy": ["0", "false", "no", ""], "case_sensitive": True},
        "browser": {"env": "BROWSER_AUTOMATION", "default_on": False, "empty_string": "off", "falsy": ["0", "false", "no", ""], "case_sensitive": True},
        "tool_search": {"env": "TOOL_SEARCH", "default_on": False, "empty_string": "off", "falsy": ["0", "false", "no", ""], "case_sensitive": True},
        "improve": {"env": "IMPROVE", "default_on": False, "empty_string": "off", "falsy": ["0", "false", "no", ""], "case_sensitive": True},
    })

    # ---- Matrix D: history.json message schema, workspace layout ----
    _write("schemas-v1/history-schema.json", ModelMessagesTypeAdapter.json_schema())
    _write("schemas-v1/workspace-layout.json", {
        "note": "thread_slug(thread_id) -> workspace subdir; history at <slug>/history.json",
        "cases": {tid: thread_slug(tid) for tid in [
            "default", "abc123", "a/b", "a_b", "user@host", "Thread With Spaces",
            "x" * 80, "unicode-éè", "",
        ]},
    })
    _write("schemas-v1/mcp-config.json", json.loads((ROOT / "projects/agent-web/mcp.json").read_text()))

    # ---- Matrix C (offline) + D: endpoints via TestModel ----
    # Use the REAL agent-web mcp.json (absolute) so the registry reflects the
    # deployment, where the server runs with CWD=projects/agent-web (see
    # Start-AgentWeb.ps1 -WorkingDirectory $root). Running from elsewhere would
    # fail to resolve the relative "mcp.json" and drop its logfire/postgres
    # entries — a capture artifact, not v1 behavior.
    real_mcp = ROOT / "projects/agent-web/mcp.json"
    for label, roster in [("code-default", "context7,deepwiki"),
                          ("deployed", "context7,deepwiki,github,logfire")]:
        settings = Settings(mcp_enable=tuple(roster.split(",")), mcp_config=real_mcp)
        app = create_app(settings=settings, model=TestModel())
        with TestClient(app) as client:
            hz = client.get("/healthz")
            mcp = client.get("/debug/mcp")
            _write(f"endpoints-v1/healthz.{label}.json", {
                "status_code": hz.status_code, "keys": sorted(hz.json().keys()),
            })
            rows = mcp.json()
            names = {r["name"] for r in rows}
            requested = roster.split(",")
            _write(f"endpoints-v1/debug-mcp.{label}.json", {
                "status_code": mcp.status_code,
                "requested": requested,
                "enabled_set": sorted(r["name"] for r in rows if r["enabled"]),
                # requested names with no registry entry — silently ignored by
                # build_registry (only a log.warning). v1 config gap when nonempty.
                "ignored": sorted(n for n in requested if n not in names),
                "servers": sorted(
                    ({"name": r["name"], "transport": r["transport"],
                      "builtin": r["builtin"], "enabled": r["enabled"]}
                     for r in rows), key=lambda r: r["name"]),
                "row_keys": sorted(rows[0].keys()) if rows else [],
            })

        # ---- Matrix C: 422 body shape (the v1 double-encoded form) ----
        if label == "code-default":
            with TestClient(app) as client:
                r = client.post("/agent", content=b"{ not valid json }",
                                headers={"content-type": "application/json"})
                body = r.text
                try:
                    parsed = json.loads(body)
                    parsed_type = type(parsed).__name__
                except json.JSONDecodeError:
                    parsed_type = "not-json"
                _write("endpoints-v1/agent-422.json", {
                    "status_code": r.status_code,
                    "content_type": r.headers.get("content-type"),
                    "body_json_loads_type": parsed_type,  # v1: 'str' (double-encoded)
                })


def capture_eval_optimizer() -> None:
    from eval_optimizer.schema import HarnessForkReport, HarnessBranchResult, ForkReport

    _write("schemas-v1/harness-fork-report-schema.json", HarnessForkReport.model_json_schema())
    _write("schemas-v1/harness-branch-result-schema.json", HarnessBranchResult.model_json_schema())
    _write("schemas-v1/fork-report-schema.json", ForkReport.model_json_schema())
    sample = HarnessForkReport(
        task="baseline sample",
        branches=[HarnessBranchResult(branch_id="b1", label="approach-a", test_pass_ratio=1.0,
                                      cost_usd=0.01, turns=3, error_count=0, preview="ok")],
        winner_branch_id="b1", any_viable=True, winner_dir=None,
    )
    _write("schemas-v1/harness-fork-report-sample.json", sample.model_dump())


if __name__ == "__main__":
    scope = sys.argv[1] if len(sys.argv) > 1 else "aw"
    if scope == "aw":
        capture_agent_web()
    elif scope == "eo":
        capture_eval_optimizer()
    else:
        raise SystemExit(f"unknown scope {scope!r} (use 'aw' or 'eo')")
