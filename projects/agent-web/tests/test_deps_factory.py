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
    a = make_deps(tmp_path, "thread-a")
    b = make_deps(tmp_path, "thread-b")
    assert a.backend is not b.backend
    assert (tmp_path / "thread-a").is_dir() and (tmp_path / "thread-b").is_dir()
    assert a.checkpoint_store is not b.checkpoint_store


def test_state_handler_protocol(tmp_path):
    d = make_deps(tmp_path, "t")
    assert isinstance(d.state, UiState)  # dataclass w/ non-optional state => StateHandler
    assert isinstance(d, WebDeps)
