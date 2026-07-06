"""ADR-0019 (plan 6.3, crit-checkpoint-persistence): the checkpoint store is
DURABLE and per-thread — FileCheckpointStore under the server-only state tree
(5.1) — so checkpoints and fork anchors survive across requests and restarts,
the storage prerequisite of the deepresearch→CopilotKit port (ISSUE-4).

Checkpoint = a saved snapshot of the conversation (id, label, messages) the
harness can rewind to; forking anchors on them (`fork:<id>`).
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_deep.features.checkpointing.store import Checkpoint

from agent_web.deps import make_deps


def _checkpoint(cp_id: str, label: str) -> Checkpoint:
    msgs = [ModelRequest(parts=[UserPromptPart(content="state before rewind")])]
    return Checkpoint(id=cp_id, label=label, turn=1, messages=msgs,
                      message_count=len(msgs), created_at=datetime.now(timezone.utc))


async def test_checkpoint_round_trip(tmp_path):
    deps_a = make_deps(tmp_path / "ws", tmp_path / "state", "cp-a")
    deps_b = make_deps(tmp_path / "ws", tmp_path / "state", "cp-b")

    await deps_a.checkpoint_store.save(_checkpoint("cp-1", "before-risky-step"))

    got = await deps_a.checkpoint_store.get("cp-1")
    assert got is not None and got.label == "before-risky-step"
    assert got.messages[0].parts[0].content == "state before rewind"
    by_label = await deps_a.checkpoint_store.get_by_label("before-risky-step")
    assert by_label is not None and by_label.id == "cp-1"

    # Isolation: thread B's store is a different directory with no checkpoints.
    assert await deps_b.checkpoint_store.count() == 0
    assert await deps_a.checkpoint_store.count() == 1

    assert await deps_a.checkpoint_store.remove("cp-1") is True
    assert await deps_a.checkpoint_store.count() == 0


async def test_checkpoints_survive_across_requests(tmp_path):
    """THE 6.3 point (v1 defect: a fresh InMemoryCheckpointStore per POST meant
    any checkpoint from run N was gone when run N+1 arrived — cross-request
    rewind and fork:<id> anchoring could never work). A checkpoint saved
    during one request is visible to the next request's fresh deps."""
    state = tmp_path / "state"
    request_1 = make_deps(tmp_path / "ws", state, "keeper")
    await request_1.checkpoint_store.save(_checkpoint("cp-9", "fork:abc123"))

    request_2 = make_deps(tmp_path / "ws", state, "keeper")  # a NEW request
    assert request_2.checkpoint_store is not request_1.checkpoint_store
    got = await request_2.checkpoint_store.get("cp-9")
    assert got is not None and got.label == "fork:abc123"


async def test_checkpoints_live_outside_agent_workspace(tmp_path):
    """ADR-0019 boundary (extends 5.1's negative test to checkpoints): the
    store lives in the server-only state tree, not under any LocalBackend
    root — agent file tools cannot read or rewrite checkpoints."""
    ws, state = tmp_path / "ws", tmp_path / "state"
    deps = make_deps(ws, state, "sneaky")
    await deps.checkpoint_store.save(_checkpoint("cp-2", "hidden"))

    assert list(ws.rglob("*.json")) == [], "checkpoint leaked into a workspace"
    assert (state / "checkpoints" / "sneaky" / "cp-2.json").exists()
    assert not state.resolve().is_relative_to(ws.resolve())


def test_vendor_prune_cap_default_pinned():
    """ADR-0019: per-thread growth is bounded by the capability's auto-prune.
    We rely on create_deep_agent's max_checkpoints default — pin it so a
    re-vendor that changes (or drops) the cap fails loudly for review."""
    import inspect

    from pydantic_deep import create_deep_agent

    param = inspect.signature(create_deep_agent).parameters["max_checkpoints"]
    assert param.default == 20
