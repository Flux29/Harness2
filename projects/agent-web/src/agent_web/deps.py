"""Per-session dependency factory — ADR-0012 risk 2, unit-tested.

One rule (harness docs/advanced/multi-user.md): isolation == distinct backend.
Each AG-UI thread gets its own LocalBackend rooted under workspaces/<thread>/,
its own checkpoint store, and its own AG-UI shared-state model (StateHandler:
a dataclass subclass of DeepAgentDeps with a non-optional `state` field).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai_backends import LocalBackend
from pydantic_deep import DeepAgentDeps, InMemoryCheckpointStore


class UiState(BaseModel):
    """Shared UI state snapshot (AG-UI state management)."""

    note: str = ""


@dataclass
class WebDeps(DeepAgentDeps):
    state: UiState = field(default_factory=UiState)


def thread_slug(thread_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", thread_id)[:64] or "default"


def make_deps(workspaces_dir: Path, thread_id: str) -> WebDeps:
    root = Path(workspaces_dir) / thread_slug(thread_id)
    root.mkdir(parents=True, exist_ok=True)
    return WebDeps(
        backend=LocalBackend(root_dir=str(root)),
        checkpoint_store=InMemoryCheckpointStore(),
    )
