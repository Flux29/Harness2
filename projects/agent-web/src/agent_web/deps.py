"""Per-session dependency factory — ADR-0012 risk 2, unit-tested.

One rule (harness docs/advanced/multi-user.md): isolation == distinct backend.
Each AG-UI thread gets its own LocalBackend rooted under workspaces/<thread>/,
its own DURABLE checkpoint store (ADR-0019: per-thread, in the 5.1 server-only
state tree — checkpoints and fork anchors survive across requests and
restarts, which a stateless-per-POST AG-UI layer requires), and its own AG-UI
shared-state model (StateHandler: a dataclass subclass of DeepAgentDeps with a
non-optional `state` field).
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai_backends import LocalBackend
from pydantic_deep import DeepAgentDeps, FileCheckpointStore

# Shared context channel (feat-improve-loop): *.md files in
# projects/agent-web/context/ are seeded into every thread workspace, so the
# harness's ContextFilesCapability injects them into every session and the
# improve pipeline's accepted proposals reach FUTURE threads. Without this,
# each thread starts from a blank workspace and improvements have no durable
# home.
_CONTEXT_DIR = Path(__file__).resolve().parents[2] / "context"


def _seed_context_files(root: Path, context_dir: Path) -> None:
    """Copy shared context files into a thread workspace.

    Copy-if-missing-or-stale: a newer shared file overwrites the workspace
    copy (thread-local edits to these files are not a supported surface —
    the shared context/ dir is the single source of truth)."""
    if not context_dir.is_dir():
        return
    for src in context_dir.glob("*.md"):
        dest = root / src.name
        if not dest.exists() or src.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(src, dest)


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


def make_deps(
    workspaces_dir: Path,
    state_dir: Path,
    thread_id: str,
    context_dir: Path | None = None,
) -> WebDeps:
    slug = thread_slug(thread_id)
    root = Path(workspaces_dir) / slug
    root.mkdir(parents=True, exist_ok=True)
    _seed_context_files(root, context_dir if context_dir is not None else _CONTEXT_DIR)
    return WebDeps(
        backend=LocalBackend(root_dir=str(root)),
        # ADR-0019: durable per-thread store, OUTSIDE every LocalBackend root
        # (same trust boundary as history, 5.1). The rewind endpoints /
        # RewindRequested handling / UI land with the deepresearch->CopilotKit
        # port (ISSUE-4); until then this is the port's storage prerequisite
        # and the fork machinery's cross-request anchor store.
        checkpoint_store=FileCheckpointStore(Path(state_dir) / "checkpoints" / slug),
    )
