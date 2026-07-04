"""ADR-0012 risk 2: the per-session deps factory, unit-tested."""
from __future__ import annotations

import pytest

from agent_web.deps import UiState, WebDeps, make_deps, thread_slug


def test_slug_sanitizes():
    assert thread_slug("../../etc/passwd") == "______etc_passwd"
    assert thread_slug("") == "default"
    assert len(thread_slug("x" * 200)) == 64


# --- Phase 3.6: red tests pinning the thread_slug collision defect (crit-thread-
# slug-collision). They FAIL on v1 and are xfail(strict) so CI stays green; when
# step 4.3 adds a content hash they will XPASS, and strict=True forces removing
# the xfail marker in that same PR. This documents the boundary before the fix.

@pytest.mark.xfail(reason="thread_slug collisions — fixed in 4.3 (add content hash)", strict=True)
def test_slug_distinguishes_slash_from_underscore():
    # 'a/b' and 'a_b' must map to DIFFERENT workspaces; v1 sanitizes both to 'a_b'.
    assert thread_slug("a/b") != thread_slug("a_b")


@pytest.mark.xfail(reason="thread_slug collisions — fixed in 4.3 (add content hash)", strict=True)
def test_slug_distinguishes_long_prefix_twins():
    # Two ids sharing a 64-char sanitized prefix must not collide; v1 truncates
    # both to the same 64 chars.
    a = thread_slug("x" * 64 + "-alpha")
    b = thread_slug("x" * 64 + "-beta")
    assert a != b


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
