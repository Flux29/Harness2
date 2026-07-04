"""Parity Matrix C (offline wire slice) + Matrix D (persistence & endpoints).

Matrix C's streaming event sequences need live SSE transcripts (baseline/sse-v1,
run at the live gates). The offline slice enforced here is the 422 body shape —
the one intentional wire diff, which flips in step 3.2 — plus the endpoint and
persistence shapes of Matrix D.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from agent_web.app import create_app
from agent_web.deps import thread_slug
from agent_web.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client_code_default():
    settings = Settings(mcp_enable=("context7", "deepwiki"))
    with TestClient(create_app(settings=settings, model=TestModel())) as c:
        yield c


# -------------------------- Matrix C: 422 body ----------------------------
def test_422_body_shape(client_code_default, baseline):
    b = baseline("endpoints-v1/agent-422.json")
    r = client_code_default.post("/agent", content=b"{ not valid json }",
                                 headers={"content-type": "application/json"})
    assert r.status_code == b["status_code"] == 422
    loaded = json.loads(r.text)
    got_type = type(loaded).__name__
    # v1 baseline is 'str' (double-encoded). Step 3.2 FLIPS this row: the body
    # becomes the actual JSON error object (list/dict). When 3.2 lands, change
    # the expected below to {"list", "dict"} and flip crit-422-encoding.
    assert got_type == b["body_json_loads_type"], (
        f"Matrix C[422-body]: body json type {got_type!r} != baseline "
        f"{b['body_json_loads_type']!r} (intentional flip is step 3.2)")


# ------------------ Matrix D: /healthz and /debug/mcp ---------------------
def test_healthz_keys_additive_only(client_code_default, baseline):
    b = baseline("endpoints-v1/healthz.code-default.json")
    r = client_code_default.get("/healthz")
    assert r.status_code == 200
    assert set(b["keys"]).issubset(set(r.json().keys())), "Matrix D[healthz]: keys are additive-only"


def test_debug_mcp_shape(client_code_default, baseline):
    b = baseline("endpoints-v1/debug-mcp.code-default.json")
    r = client_code_default.get("/debug/mcp")
    assert r.status_code == 200
    rows = r.json()
    assert set(b["row_keys"]).issubset(set(rows[0].keys())), "Matrix D[debug-mcp]: row keys additive-only"
    got = {row["name"]: row["enabled"] for row in rows}
    for srv in b["servers"]:
        assert got.get(srv["name"]) == srv["enabled"], f"Matrix D[debug-mcp]: {srv['name']} enabled-state drifted"


def test_debug_mcp_deployed_roster_reflects_v1_reality(baseline):
    """Matrix D deployment-config row. v1 reality (server CWD = projects/agent-web,
    so mcp.json resolves): the deployed roster enables all four —
    {context7, deepwiki, github, logfire}. logfire is registered from mcp.json as
    a stdio server; nothing is ignored. This matches the PDR's claimed roster.
    See manifest disc-mcp-config-cwd-relative for the CWD-dependence caveat."""
    b = baseline("endpoints-v1/debug-mcp.deployed.json")
    assert b["ignored"] == [], "v1 reality: with mcp.json present, nothing is ignored"
    real_mcp = ROOT / "projects/agent-web/mcp.json"
    settings = Settings(mcp_enable=("context7", "deepwiki", "github", "logfire"),
                        mcp_config=real_mcp)
    with TestClient(create_app(settings=settings, model=TestModel())) as c:
        rows = c.get("/debug/mcp").json()
    enabled = sorted(r["name"] for r in rows if r["enabled"])
    assert enabled == b["enabled_set"] == ["context7", "deepwiki", "github", "logfire"], (
        "Matrix D[deployment-config]: enabled set drifted from v1 reality")


# ------------------ Matrix D: workspace layout / slug ---------------------
def test_workspace_layout_noncolliding_stable(baseline):
    """Previously-non-colliding ids must map to the SAME directory. The slug fn
    changes in 4.3 for COLLIDING ids only; this pins the non-colliding cases."""
    b = baseline("schemas-v1/workspace-layout.json")["cases"]
    for tid, expected_slug in b.items():
        # 'a/b' vs 'a_b' collide in v1 (both -> 'a_b'); that pair is the 4.3
        # target and is exercised by the red tests, not asserted stable here.
        if tid in ("a/b", "a_b"):
            continue
        assert thread_slug(tid) == expected_slug, f"Matrix D[workspace]: slug({tid!r}) drifted"


def test_history_schema_stable(baseline):
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    b = baseline("schemas-v1/history-schema.json")
    # Message schema is identical throughout (location changes in 5.1, not shape).
    assert ModelMessagesTypeAdapter.json_schema() == b, "Matrix D[history]: message schema drifted"
