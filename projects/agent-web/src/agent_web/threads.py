"""Thread listing + transcript payloads (feat-thread-persistence, ISSUE-4).

Serves the manual thread-persistence UI: GET /threads (sidebar list) and
GET /threads/{id}/messages (transcript rehydration + pending-interrupt
recovery). No FastAPI imports — pure functions over Settings and the history
store, unit-testable without the app.

Reads for a single thread ALWAYS go through ``history.load`` (dual-write-
window correct). The list is served from the derived index maintained by
``history.save``; when the index is missing or unreadable it regenerates
wholesale from disk — a sweep that includes the legacy v1
``workspaces/<slug>/history.json`` copies, which is exactly the pre-5.1
dormant-thread backfill.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ToolCallPart
from pydantic_ai.ui.ag_ui import AGUIAdapter

from . import history
from .settings import Settings

log = logging.getLogger("agent_web.threads")

# The AG-UI approval-interrupt id convention. pydantic_ai.ui.ag_ui._interrupt
# is a private module, so the prefix is hard-coded here rather than imported;
# drift is pinned by test_pending_interrupt_parity, which compares a derived
# interrupt against a live paused run's RUN_FINISHED outcome on every CI run.
_INTERRUPT_PREFIX = "int-"


def list_threads(
    settings: Settings, running_ids: frozenset[str] | set[str] = frozenset()
) -> list[dict[str, Any]]:
    entries = _load_or_regenerate_index(settings)
    out: list[dict[str, Any]] = []
    for slug, e in entries.items():
        thread_id = e.get("thread_id", slug)
        out.append({
            "id": thread_id,
            "updated_at": e.get("updated_at", ""),
            "message_count": e.get("message_count", 0),
            "title": e.get("title", "(untitled)"),
            "has_pending_interrupts": bool(e.get("has_pending_interrupts", False)),
            "running": thread_id in running_ids,
        })
    out.sort(key=lambda t: t["updated_at"], reverse=True)
    return out


def thread_payload(settings: Settings, thread_id: str) -> dict[str, Any] | None:
    """Transcript + pending interrupts for one thread; None -> 404."""
    messages = history.load(settings, thread_id)
    if messages is None:
        return None
    ui_messages = AGUIAdapter.dump_messages(messages)
    return {
        "id": thread_id,
        "messages": [m.model_dump(by_alias=True, exclude_none=True) for m in ui_messages],
        "interrupts": [
            _interrupt_dict(p) for p in history.pending_tool_calls(messages)
        ],
    }


def _interrupt_dict(part: ToolCallPart) -> dict[str, Any]:
    """Shape a pending approval as the AG-UI Interrupt the live wire emits
    (camelCase, matching @ag-ui/client's Interrupt type)."""
    return {
        "id": f"{_INTERRUPT_PREFIX}{part.tool_call_id}",
        "reason": "tool_call",
        "toolCallId": part.tool_call_id,
        "message": f"Approve {part.tool_name}({part.args_as_json_str()})?",
        "responseSchema": {
            "type": "object",
            "properties": {
                "approved": {"type": "boolean"},
                "editedArgs": {"type": "object"},
                "reason": {"type": "string"},
            },
            "required": ["approved"],
        },
    }


def _load_or_regenerate_index(settings: Settings) -> dict[str, dict[str, Any]]:
    p = history.index_path(settings.state_dir)
    try:
        return json.loads(p.read_text(encoding="utf-8"))["threads"]
    except (OSError, ValueError, KeyError):
        pass
    entries = _regenerate_index(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"threads": entries}, indent=2), encoding="utf-8")
    return entries


def _regenerate_index(settings: Settings) -> dict[str, dict[str, Any]]:
    """Rebuild the index from disk: the server tree plus the legacy v1
    workspace copies (the pre-5.1 backfill). Disk regeneration cannot recover
    an exotic ORIGINAL thread id from a hash-suffixed slug — those entries
    key by slug (a fixed point of thread_slug, so they still load); ids
    refresh to the original on the thread's next save."""
    entries: dict[str, dict[str, Any]] = {}

    def _ingest(path: Path, slug: str) -> None:
        try:
            messages: list[ModelMessage] = ModelMessagesTypeAdapter.validate_json(
                path.read_bytes()
            )
        except (OSError, ValueError):
            log.warning("threads-index regenerate: skipping unreadable history %s", path)
            return
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        entries[slug] = history.index_entry(
            slug, messages, created_at=mtime, updated_at=mtime
        )

    state_hist = Path(settings.state_dir) / "history"
    if state_hist.is_dir():
        for f in state_hist.glob("*.json"):
            _ingest(f, f.stem)
    workspaces = Path(settings.workspaces_dir)
    if workspaces.is_dir():
        for f in workspaces.glob("*/history.json"):
            if f.parent.name not in entries:  # the server copy wins
                _ingest(f, f.parent.name)
    return entries
