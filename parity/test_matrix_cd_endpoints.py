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
    # require_loopback_host=False: TestClient posts over a synthetic Host
    # (testserver); the ADR-0020 rebinding check is exercised in agent-web's
    # security suite, not the Matrix C/D parity slice.
    settings = Settings(mcp_enable=("context7", "deepwiki"), require_loopback_host=False)
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
    # ROW FLIPPED by step 3.2 (crit-422-encoding). v1 baseline was 'str' (the
    # double-encoded body); the fix makes the body the actual JSON error object,
    # so json.loads() now yields a list/dict. The baseline file is kept as the v1
    # witness (body_json_loads_type == 'str'); this assertion encodes the new,
    # intended shape.
    assert b["body_json_loads_type"] == "str"  # v1 witness unchanged
    assert got_type in ("list", "dict"), (
        f"Matrix C[422-body]: post-3.2 body must be a JSON object, got {got_type!r}")


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
    """Matrix D[workspace-layout] — ROW FLIPPED by step 4.3 (crit-thread-slug-
    collision). Non-colliding ids keep their exact v1 directory; a pure
    function can only know an id is collision-FREE when sanitization leaves it
    untouched (distinct clean ids stay distinct), so that is the stable class.
    Every id the v1 sanitizer altered or truncated is in a collision class by
    construction ('a/b' folded onto clean 'a_b'; 64-char-prefix twins folded
    together) and relocates ONCE, deterministically, to
    sanitized[:48] + '-' + sha256(id)[:12]."""
    import re as _re

    b = baseline("schemas-v1/workspace-layout.json")["cases"]
    new_slugs: dict[str, str] = {}
    for tid, v1_slug in b.items():
        got = thread_slug(tid)
        new_slugs[tid] = got
        if tid == "" or _re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tid):
            assert got == v1_slug, f"Matrix D[workspace]: clean id {tid!r} drifted"
        else:
            # Relocated collision class: v1 prefix preserved, 12-hex suffix.
            assert got == f"{v1_slug[:48]}-{got[-12:]}", (
                f"Matrix D[workspace]: {tid!r} lost its sanitized v1 prefix")
            assert _re.fullmatch(r"[0-9a-f]{12}", got[-12:]), (
                f"Matrix D[workspace]: {tid!r} suffix is not a content hash")
            assert got == thread_slug(tid), "slug must be deterministic"
    # The 4.3 point: the baseline's colliding pair no longer shares a directory.
    assert new_slugs["a/b"] != new_slugs["a_b"]
    assert len(set(new_slugs.values())) == len(set(b.values())) + 1  # pair split


def test_history_schema_stable(baseline):
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    b = baseline("schemas-v1/history-schema.json")
    # Message schema is identical throughout (location changes in 5.1, not shape).
    assert ModelMessagesTypeAdapter.json_schema() == b, "Matrix D[history]: message schema drifted"
