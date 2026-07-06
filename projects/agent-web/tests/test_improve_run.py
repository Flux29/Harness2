"""feat-improve-loop: the headless improve runner's offline surfaces.

The LLM analysis itself is live-only; these tests pin the deterministic
plumbing — session staging (layout + mtime preservation) and the zero-session
fast path of the CLI (no model call, no state written)."""
from __future__ import annotations

import json

from agent_web.improve_run import CONTEXT_FILES, main, stage_sessions


def _write_history(history_dir, slug, payload):
    history_dir.mkdir(parents=True, exist_ok=True)
    f = history_dir / f"{slug}.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    return f


def test_stage_sessions_layout(tmp_path):
    history = tmp_path / "history"
    src_a = _write_history(history, "thread-a", [{"role": "user"}])
    _write_history(history, "thread-b", [{"role": "assistant"}])

    staging = tmp_path / "staged"
    assert stage_sessions(history, staging) == 2
    staged_a = staging / "thread-a" / "messages.json"
    assert json.loads(staged_a.read_text(encoding="utf-8")) == [{"role": "user"}]
    assert (staging / "thread-b" / "messages.json").exists()
    # copy2 preserves mtime — the analyzer's day-window discovery depends on it.
    assert abs(staged_a.stat().st_mtime - src_a.stat().st_mtime) < 1.0


def test_stage_sessions_rebuilds_staging(tmp_path):
    history = tmp_path / "history"
    _write_history(history, "thread-a", [])
    staging = tmp_path / "staged"
    stage_sessions(history, staging)
    (staging / "stale-session").mkdir()  # derived state must not accumulate
    stage_sessions(history, staging)
    assert not (staging / "stale-session").exists()


def test_stage_sessions_missing_history_dir(tmp_path):
    assert stage_sessions(tmp_path / "absent", tmp_path / "staged") == 0


def test_cli_zero_sessions_is_offline_noop(tmp_path, capsys):
    """With no histories, the runner exits 0 before any model call and writes
    no improve state — safe to run offline/in CI."""
    assert main(["--days", "1", "--state-dir", str(tmp_path / "state")]) == 0
    out = capsys.readouterr().out
    assert "Staged 0 session(s)" in out
    assert "Nothing to analyze." in out


def test_proposals_target_the_shared_context_dir():
    """Applied proposals must land in context/ (the deps-factory seed source),
    never a per-thread workspace."""
    assert all(v.startswith("context/") for v in CONTEXT_FILES.values())
