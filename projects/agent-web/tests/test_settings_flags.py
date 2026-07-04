"""Phase 3.3 — unified env-flag parsing (`_flag`).

Covers the whole value table for both default polarities. The semantic-parity
requirement (Matrix A): every v1-valid value resolves identically except the
documented fix `False`/`FALSE` -> off.
"""
from __future__ import annotations

import pytest

from agent_web.settings import _flag


@pytest.mark.parametrize(
    "raw, default_false, default_true",
    [
        ("1", True, True),
        ("0", False, False),
        ("true", True, True),
        ("false", False, False),
        ("False", False, False),   # the fix: case-insensitive, no longer "on"
        ("FALSE", False, False),   # the fix
        ("no", False, False),
        ("yes", True, True),
        ("on", True, True),
        ("off", False, False),
        ("", False, True),         # empty string -> the flag's default (identical for all flags)
        ("  1  ", True, True),     # whitespace-tolerant
        ("banana", False, True),   # unknown -> default (never accidental-on for a gated flag)
    ],
)
def test_flag_table(monkeypatch, raw, default_false, default_true):
    monkeypatch.setenv("X_FLAG", raw)
    assert _flag("X_FLAG", False) is default_false
    assert _flag("X_FLAG", True) is default_true


def test_flag_unset_returns_default(monkeypatch):
    monkeypatch.delenv("X_FLAG", raising=False)
    assert _flag("X_FLAG", False) is False
    assert _flag("X_FLAG", True) is True


def test_execute_false_is_off(monkeypatch):
    """The headline v1 bug: EXECUTE=False (capital F) must NOT enable execution."""
    monkeypatch.setenv("EXECUTE", "False")
    assert _flag("EXECUTE", False) is False


def test_fork_config_centralized_defaults():
    """Phase 3.5: fork knobs live on Settings and default conservatively.
    build_agent reads settings.fork_* (exercised by test_agent_build)."""
    from agent_web.settings import Settings

    s = Settings()
    assert s.fork_test_command == "pytest -q"
    assert s.fork_max_branches == 4
    assert s.fork_test_timeout_s == 60.0
    assert s.fork_branch_budget_usd == 0.75
    assert s.fork_aggregate_budget_usd == 2.5
