"""ADR-0012 risk 2: the per-session deps factory, unit-tested."""
from __future__ import annotations

from agent_web.deps import UiState, WebDeps, make_deps, thread_slug


def test_slug_sanitizes():
    assert thread_slug("../../etc/passwd") == "______etc_passwd"
    assert thread_slug("") == "default"
    assert len(thread_slug("x" * 200)) == 64


def test_distinct_threads_distinct_backends(tmp_path):
    a = make_deps(tmp_path, "thread-a")
    b = make_deps(tmp_path, "thread-b")
    assert a.backend is not b.backend
    assert (tmp_path / "thread-a").is_dir() and (tmp_path / "thread-b").is_dir()
    assert a.checkpoint_store is not b.checkpoint_store


def test_state_handler_protocol(tmp_path):
    d = make_deps(tmp_path, "t")
    assert isinstance(d.state, UiState)  # dataclass w/ non-optional state => StateHandler
    assert isinstance(d, WebDeps)
