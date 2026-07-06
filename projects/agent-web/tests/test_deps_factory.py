"""ADR-0012 risk 2: the per-session deps factory, unit-tested."""
from __future__ import annotations

from agent_web.deps import UiState, WebDeps, make_deps, thread_slug


def test_slug_sanitizes():
    # Clean ids (sanitization no-op, <=64 chars) keep their exact v1 directory.
    assert thread_slug("abc-123_X") == "abc-123_X"
    assert thread_slug("") == "default"
    # Modified ids relocate to sanitized[:48] + '-' + sha256(id)[:12] (4.3).
    slug = thread_slug("../../etc/passwd")
    assert slug.startswith("______etc_passwd-")
    assert len(slug) == len("______etc_passwd") + 13
    assert len(thread_slug("x" * 200)) == 48 + 1 + 12
    # Deterministic: same id, same workspace, every time.
    assert thread_slug("../../etc/passwd") == slug


# --- Phase 3.6 red tests, flipped GREEN by 4.3 (crit-thread-slug-collision):
# the content-hash suffix distinguishes ids whose sanitized forms collided.
# strict xfail markers removed in the 4.3 commit, as the 3.6 note required.

def test_slug_distinguishes_slash_from_underscore():
    # 'a/b' and 'a_b' must map to DIFFERENT workspaces; v1 sanitized both to 'a_b'.
    assert thread_slug("a/b") != thread_slug("a_b")


def test_slug_distinguishes_long_prefix_twins():
    # Two ids sharing a 64-char sanitized prefix must not collide; v1 truncated
    # both to the same 64 chars.
    a = thread_slug("x" * 64 + "-alpha")
    b = thread_slug("x" * 64 + "-beta")
    assert a != b


def test_distinct_threads_distinct_backends(tmp_path):
    state = tmp_path / "state"
    a = make_deps(tmp_path / "ws", state, "thread-a")
    b = make_deps(tmp_path / "ws", state, "thread-b")
    assert a.backend is not b.backend
    assert (tmp_path / "ws" / "thread-a").is_dir() and (tmp_path / "ws" / "thread-b").is_dir()
    assert a.checkpoint_store is not b.checkpoint_store
    # ADR-0019: durable stores live in per-thread dirs under the state tree.
    assert a.checkpoint_store._dir != b.checkpoint_store._dir


def test_state_handler_protocol(tmp_path):
    d = make_deps(tmp_path / "ws", tmp_path / "state", "t")
    assert isinstance(d.state, UiState)  # dataclass w/ non-optional state => StateHandler
    assert isinstance(d, WebDeps)


# --- feat-improve-loop: shared context channel ------------------------------

def test_make_deps_seeds_shared_context_files(tmp_path):
    """New thread workspaces receive the shared context/*.md files, and a
    newer shared file overwrites a stale workspace copy — the channel through
    which improve-run proposals reach future sessions."""
    import os
    import time

    from agent_web.deps import make_deps

    ctx = tmp_path / "context"
    ctx.mkdir()
    (ctx / "AGENTS.md").write_text("v1 rules", encoding="utf-8")

    ws = tmp_path / "workspaces"
    make_deps(ws, tmp_path / "state", "t1", context_dir=ctx)
    seeded = ws / "t1" / "AGENTS.md"
    assert seeded.read_text(encoding="utf-8") == "v1 rules"

    # Shared update propagates on the thread's next request.
    (ctx / "AGENTS.md").write_text("v2 rules", encoding="utf-8")
    os.utime(ctx / "AGENTS.md", (time.time() + 5, time.time() + 5))
    make_deps(ws, tmp_path / "state", "t1", context_dir=ctx)
    assert seeded.read_text(encoding="utf-8") == "v2 rules"


def test_make_deps_without_context_dir_is_fine(tmp_path):
    from agent_web.deps import make_deps

    deps = make_deps(tmp_path / "ws", tmp_path / "state", "t1",
                     context_dir=tmp_path / "absent")
    assert deps.backend is not None
