"""ADR-0020 — composed security posture: the /agent request-authenticity guard.

The headline test (`test_verified_cross_origin_driveby_now_403`) replays the
exact request this ADR verified was PROCESSED against the pre-guard code
(text/plain + foreign Origin, HTTP 200, history written) and asserts it is now
refused before any run/history/model work.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import replace

import httpx
from pydantic_ai.models.test import TestModel

from agent_web.app import _loopback_host, create_app
from helpers import make_settings, run_input_json


def _app(settings, model=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return create_app(settings=settings, model=model or TestModel(call_tools=[]))


async def _post(app, body, headers, base_url="http://127.0.0.1:8801"):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url
        ) as client:
            return await client.post("/agent", content=body, headers=headers)


# ------------------------- the verified drive-by --------------------------

async def test_verified_cross_origin_driveby_now_403(tmp_path):
    """The exact probe that returned 200 + wrote history against pre-guard code:
    a browser 'simple request' (text/plain, foreign Origin, no preflight)."""
    settings = make_settings(tmp_path)
    app = _app(settings)
    r = await _post(app, run_input_json("drive-by", thread_id="csrf"),
                    {"content-type": "text/plain;charset=UTF-8",
                     "origin": "https://evil.example"})
    assert r.status_code == 403
    assert json.loads(r.text)["error"] == "content-type must be application/json"
    # the side effect never happened
    assert not (tmp_path / "state" / "history" / "csrf.json").exists()


async def test_preflightable_cross_origin_json_refused_by_origin(tmp_path):
    """A cross-origin JSON POST (would require a preflight the browser blocks);
    server-side Origin check refuses it as defense in depth."""
    app = _app(make_settings(tmp_path))
    r = await _post(app, run_input_json("x", thread_id="o"),
                    {"content-type": "application/json", "origin": "https://evil.example"})
    assert r.status_code == 403
    assert json.loads(r.text)["error"] == "origin not allowed"


# ------------------------------ happy paths -------------------------------

async def test_same_origin_json_ok(tmp_path):
    """The bundled same-origin UI: JSON, Origin == Host. Unchanged behavior."""
    app = _app(make_settings(tmp_path))
    r = await _post(app, run_input_json("hi", thread_id="ok"),
                    {"content-type": "application/json",
                     "origin": "http://127.0.0.1:8801", "host": "127.0.0.1:8801"})
    assert r.status_code == 200 and "RUN_FINISHED" in r.text


async def test_allowlisted_dev_origin_ok(tmp_path):
    """The dev frontend origin (cors_origins default) hitting the backend."""
    settings = replace(make_settings(tmp_path), cors_origins=("http://localhost:3000",))
    app = _app(settings)
    r = await _post(app, run_input_json("hi", thread_id="dev"),
                    {"content-type": "application/json",
                     "origin": "http://localhost:3000", "host": "127.0.0.1:8801"})
    assert r.status_code == 200 and "RUN_FINISHED" in r.text


async def test_no_origin_json_ok(tmp_path):
    """Non-browser / server-to-server client: no Origin header, JSON body."""
    app = _app(make_settings(tmp_path))
    r = await _post(app, run_input_json("hi", thread_id="srv"),
                    {"content-type": "application/json"})
    assert r.status_code == 200 and "RUN_FINISHED" in r.text


# --------------------------- DNS-rebinding host ---------------------------

async def test_rebinding_host_refused(tmp_path):
    """DNS rebinding makes Origin AND Host the attacker's rebound domain, so the
    same-origin check passes — only the loopback-Host rule catches it."""
    settings = replace(make_settings(tmp_path), require_loopback_host=True)
    app = _app(settings)
    r = await _post(app, run_input_json("x", thread_id="rb"),
                    {"content-type": "application/json",
                     "origin": "http://evil.example", "host": "evil.example"},
                    base_url="http://evil.example")
    assert r.status_code == 403
    assert json.loads(r.text)["error"] == "host is not loopback"


def test_loopback_host_helper():
    assert _loopback_host("127.0.0.1:8801")
    assert _loopback_host("localhost")
    assert _loopback_host("[::1]:8801")
    assert not _loopback_host("evil.example")
    assert not _loopback_host("10.0.0.5:8801")
    assert not _loopback_host("")


# ------------------------------ bearer token ------------------------------

async def test_token_required_when_set(tmp_path):
    settings = replace(make_settings(tmp_path), agent_token="s3cret")
    app = _app(settings)
    # missing token -> 403
    r = await _post(app, run_input_json("x", thread_id="t"),
                    {"content-type": "application/json"})
    assert r.status_code == 403
    assert json.loads(r.text)["error"] == "missing or invalid bearer token"
    # correct token -> 200
    r2 = await _post(app, run_input_json("x", thread_id="t"),
                     {"content-type": "application/json", "authorization": "Bearer s3cret"})
    assert r2.status_code == 200 and "RUN_FINISHED" in r2.text


async def test_wrong_token_refused(tmp_path):
    settings = replace(make_settings(tmp_path), agent_token="s3cret")
    app = _app(settings)
    r = await _post(app, run_input_json("x", thread_id="t"),
                    {"content-type": "application/json", "authorization": "Bearer nope"})
    assert r.status_code == 403
