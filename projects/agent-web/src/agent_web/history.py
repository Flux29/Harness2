"""Server-owned message history, keyed by AG-UI thread id (ADR-0012 trust model).

Client-sent history is untrusted; this store is authoritative. JSON file per
thread under the thread's workspace dir — same isolation boundary as files.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from .deps import thread_slug


def _path(workspaces_dir: Path, thread_id: str) -> Path:
    return Path(workspaces_dir) / thread_slug(thread_id) / "history.json"


def load(workspaces_dir: Path, thread_id: str) -> list[ModelMessage] | None:
    p = _path(workspaces_dir, thread_id)
    if not p.exists():
        return None
    return ModelMessagesTypeAdapter.validate_json(p.read_bytes())


def save(workspaces_dir: Path, thread_id: str, messages: list[ModelMessage]) -> None:
    p = _path(workspaces_dir, thread_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(ModelMessagesTypeAdapter.dump_json(messages, indent=2))
