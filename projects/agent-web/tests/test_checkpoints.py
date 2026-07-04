"""ADR-0015 leftover: per-session checkpoint store round-trips.

Checkpoint = a saved snapshot of the conversation (id, label, messages) the
harness can rewind to; forking anchors on them (`fork:<id>`).
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_deep.features.checkpointing.store import Checkpoint

from agent_web.deps import make_deps


async def test_checkpoint_round_trip(tmp_path):
    deps_a = make_deps(tmp_path, "cp-a")
    deps_b = make_deps(tmp_path, "cp-b")

    msgs = [ModelRequest(parts=[UserPromptPart(content="state before rewind")])]
    await deps_a.checkpoint_store.save(Checkpoint(
        id="cp-1", label="before-risky-step", turn=1, messages=msgs,
        message_count=len(msgs), created_at=datetime.now(timezone.utc),
    ))

    got = await deps_a.checkpoint_store.get("cp-1")
    assert got is not None and got.label == "before-risky-step"
    assert got.messages[0].parts[0].content == "state before rewind"
    by_label = await deps_a.checkpoint_store.get_by_label("before-risky-step")
    assert by_label is not None and by_label.id == "cp-1"

    # Isolation: thread B's store is a different object with no checkpoints.
    assert await deps_b.checkpoint_store.count() == 0
    assert await deps_a.checkpoint_store.count() == 1

    assert await deps_a.checkpoint_store.remove("cp-1") is True
    assert await deps_a.checkpoint_store.count() == 0
