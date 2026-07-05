"""Per-session dependency factory — ADR-0012 risk 2, unit-tested.

One rule (harness docs/advanced/multi-user.md): isolation == distinct backend.
Each AG-UI thread gets its own LocalBackend rooted under workspaces/<thread>/,
its own checkpoint store, and its own AG-UI shared-state model (StateHandler:
a dataclass subclass of DeepAgentDeps with a non-optional `state` field).
"""
from __future__ import annotations

import hashlib
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
    """Map a thread id to its workspace directory name (Phase 4.3,
    crit-thread-slug-collision).

    Ids the sanitizer leaves untouched (<=64 chars) are injective by identity
    and keep their exact v1 directory. Any id that sanitization ALTERS or
    truncation would fold is in a collision class by construction ('a/b' and
    'a_b' both slugged to 'a_b' in v1; 64-char-prefix twins folded together),
    so those relocate — once, deterministically — to a hash-suffixed form.
    Harness1 threads with such exotic ids won't resume their old workspaces;
    accepted for the fork (see changelog note in the 4.3 commit)."""
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", thread_id)
    if not sanitized:
        return "default"
    if sanitized == thread_id and len(sanitized) <= 64:
        return sanitized
    digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:12]
    return f"{sanitized[:48]}-{digest}"


def make_deps(workspaces_dir: Path, thread_id: str) -> WebDeps:
    root = Path(workspaces_dir) / thread_slug(thread_id)
    root.mkdir(parents=True, exist_ok=True)
    return WebDeps(
        backend=LocalBackend(root_dir=str(root)),
        checkpoint_store=InMemoryCheckpointStore(),
    )
