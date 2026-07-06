"""Phase 4.2 (crit-retry-coverage, ADR-0008) — the docstring's retry claim is
now true: every OpenAI-compatible client this project constructs rides a shared
tenacity-retrying httpx transport, INCLUDING memory_pg's embeddings client.
(The `provider:model` pass-through branch is explicitly out of scope — the
docstring was narrowed to say so in the same commit.) Offline: no requests."""
from __future__ import annotations

from eval_optimizer.models import _retrying_http_client, _retrying_sync_http_client


def test_async_retrying_client_uses_tenacity_transport():
    from httpx import AsyncClient
    from pydantic_ai.retries import AsyncTenacityTransport

    c = _retrying_http_client()
    assert isinstance(c, AsyncClient)
    assert isinstance(c._transport, AsyncTenacityTransport)


def test_sync_retrying_client_uses_tenacity_transport():
    from httpx import Client
    from pydantic_ai.retries import TenacityTransport

    c = _retrying_sync_http_client()
    assert isinstance(c, Client)
    assert isinstance(c._transport, TenacityTransport)


def test_memory_embed_client_rides_retrying_transport(monkeypatch):
    """The embedding client was the docstring's coverage lie: a bare OpenAI()
    client with the default (non-retrying) transport. It now shares the sync
    retrying client (lru-cached, so identity-comparable)."""
    from eval_optimizer.memory_pg import Memory

    m = Memory()  # constructs clients only; no connection is opened
    assert m._embed_client._client is _retrying_sync_http_client()
