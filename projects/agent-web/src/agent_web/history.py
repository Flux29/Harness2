"""Server-owned message history, keyed by AG-UI thread id (ADR-0012 trust model).

Client-sent history is untrusted; this store is authoritative. Phase 5.1
(crit-history-agent-writable): the authoritative copy lives in a server-only
tree — ``STATE_DIR/history/<slug>.json`` — that is NOT inside any LocalBackend
root, so agent file tools can never read or rewrite it.

Migration from the v1 location (``<workspace>/history.json``, inside the
agent-writable root) is a PARALLEL-RUN, not a hard cutover: with
``HISTORY_DUAL_WRITE=1`` every save writes BOTH copies and diffs the previous
pair first (divergence -> loud log + a ledger the live parity run asserts
empty), while reads stay on the v1 copy. After N=5 clean sessions the flag is
removed: reads and writes cut over to the server-only tree. The deliberate
write-path duplication is a dated Gate 4 allowlist entry whose expiry IS the
cutover deadline. Migration choice (stated per the plan): no one-shot file
relocation — the window itself migrates active threads (every save writes the
complete message list), and dormant threads restart fresh after cutover.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)

from .deps import thread_slug
from .settings import Settings

log = logging.getLogger("agent_web.history")


def state_path(state_dir: Path, thread_id: str) -> Path:
    """The server-only authoritative copy — outside every LocalBackend root."""
    return Path(state_dir) / "history" / f"{thread_slug(thread_id)}.json"


def workspace_path(workspaces_dir: Path, thread_id: str) -> Path:
    """The v1 location — INSIDE the agent-writable workspace. Written only
    while the dual-write window is open; never after cutover."""
    return Path(workspaces_dir) / thread_slug(thread_id) / "history.json"


def divergence_ledger(state_dir: Path) -> Path:
    return Path(state_dir) / "history" / "_divergences.log"


def load(settings: Settings, thread_id: str) -> list[ModelMessage] | None:
    # Reads cut over only AFTER the window: while dual-writing, the v1 copy
    # stays authoritative (observed equivalence before trust — 5.1).
    p = (workspace_path(settings.workspaces_dir, thread_id)
         if settings.history_dual_write
         else state_path(settings.state_dir, thread_id))
    if not p.exists():
        return None
    return ModelMessagesTypeAdapter.validate_json(p.read_bytes())


def save(settings: Settings, thread_id: str, messages: list[ModelMessage]) -> None:
    data = ModelMessagesTypeAdapter.dump_json(messages, indent=2)
    if settings.history_dual_write:
        _diff_existing_copies(settings, thread_id)
        _save_workspace_copy(settings.workspaces_dir, thread_id, data)
    _save_state_copy(settings.state_dir, thread_id, data)
    _index_upsert(settings, thread_id, messages)


# --- Thread index (feat-thread-persistence) ---------------------------------
# state/threads-index.json records the ORIGINAL thread id (a hash-suffixed
# slug cannot recover it) plus the list metadata GET /threads serves, so
# listing never parses every history file. The index is DERIVED state:
# threads.py regenerates it wholesale (incl. the pre-5.1 workspace backfill)
# whenever it is missing or unreadable.


def index_path(state_dir: Path) -> Path:
    return Path(state_dir) / "threads-index.json"


def title_of(messages: list[ModelMessage]) -> str:
    """Thread display title: the first user prompt, truncated."""
    for m in messages:
        if isinstance(m, ModelRequest):
            for part in m.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    t = part.content.strip()
                    return (t[:77] + "...") if len(t) > 80 else t
    return "(untitled)"


def pending_tool_calls(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Unresolved approval pause: the history ends on a ModelResponse whose
    tool calls never received returns. That is the ONLY trailing-call state
    on_complete persists (a normal run ends with returns + final text; a
    mid-run crash saves nothing), so this doubles as the pending-interrupt
    derivation for GET /threads/{id}/messages."""
    if not messages:
        return []
    last = messages[-1]
    if isinstance(last, ModelResponse):
        return [p for p in last.parts if isinstance(p, ToolCallPart)]
    return []


def index_entry(thread_id: str, messages: list[ModelMessage], *,
                created_at: str, updated_at: str) -> dict:
    return {
        "thread_id": thread_id,
        "slug": thread_slug(thread_id),
        "message_count": len(messages),
        "title": title_of(messages),
        "has_pending_interrupts": bool(pending_tool_calls(messages)),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _index_upsert(settings: Settings, thread_id: str, messages: list[ModelMessage]) -> None:
    p = index_path(settings.state_dir)
    try:
        entries = json.loads(p.read_text(encoding="utf-8")).get("threads", {})
    except (OSError, ValueError):
        entries = {}
    slug = thread_slug(thread_id)
    now = datetime.now(timezone.utc).isoformat()
    created = entries.get(slug, {}).get("created_at", now)
    entries[slug] = index_entry(thread_id, messages, created_at=created, updated_at=now)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"threads": entries}, indent=2), encoding="utf-8")


def _save_state_copy(state_dir: Path, thread_id: str, data: bytes) -> Path:
    p = state_path(state_dir, thread_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _save_workspace_copy(workspaces_dir: Path, thread_id: str, data: bytes) -> Path:
    # Gate 4: deliberately the structural twin of _save_state_copy so the
    # dual-write duplication is MACHINE-VISIBLE to the dup scanner — its
    # dated allowlist entry (owner 5.1) expires with the migration window.
    p = workspace_path(workspaces_dir, thread_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _diff_existing_copies(settings: Settings, thread_id: str) -> bool:
    """Parallel-run diff (5.1): before overwriting, the two PREVIOUS copies
    must agree. A mismatch means the workspace copy drifted since the last
    save — agent tampering or a pipeline bug. Log loudly and append to the
    ledger the live parity run asserts empty."""
    old = workspace_path(settings.workspaces_dir, thread_id)
    new = state_path(settings.state_dir, thread_id)
    if not (old.exists() and new.exists()):
        return True
    if old.read_bytes() == new.read_bytes():
        return True
    log.error(
        "history dual-write DIVERGENCE for thread %r: workspace copy differs "
        "from the server-only copy (tampering or pipeline bug). The live "
        "parity run fails on a non-empty ledger.",
        thread_id,
    )
    ledger = divergence_ledger(settings.state_dir)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {thread_slug(thread_id)}\n")
    return False
