"""Offline smoke tests — no network, no API key required."""
from __future__ import annotations

import pytest

from eval_optimizer.agents import Verdict


def test_verdict_roundtrip() -> None:
    v = Verdict(passed=False, score=40, issues=["criterion 2 unmet"], suggested_fixes=["strip punctuation"])
    assert v.passed is False
    assert v.score == 40
    assert v.issues == ["criterion 2 unmet"]


def test_verdict_score_bounds() -> None:
    with pytest.raises(ValueError):
        Verdict(passed=True, score=101)


def test_settings_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    from eval_optimizer.config import Settings

    with pytest.raises(RuntimeError):
        Settings.from_env()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    # This tests CODE defaults, so shield it from the developer's real .env
    # (config.py load_dotenv() puts .env values into os.environ at import).
    for var in ("GLM_MODEL", "EMBED_DIM", "NVIDIA_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    from eval_optimizer.config import Settings

    s = Settings.from_env()
    assert s.glm_model == "z-ai/glm-5.2"
    assert s.embed_dim == 1024
    assert s.nvidia_base_url.endswith("/v1")


def test_fork_config_centralized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 3.5: fork knobs come from the single declared Settings, defaults
    preserving forking.py's previous hardcoded values."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    for var in ("FORK_MAX_BRANCHES", "FORK_TEST_COMMAND", "FORK_TEST_TIMEOUT_S",
                "FORK_PER_BRANCH_BUDGET_USD", "FORK_AGGREGATE_BUDGET_USD"):
        monkeypatch.delenv(var, raising=False)
    from eval_optimizer.config import Settings

    s = Settings.from_env()
    assert s.fork_max_branches == 8
    assert s.fork_test_command == "pytest -q"
    assert s.fork_test_timeout_s == 90.0
    assert s.fork_per_branch_budget_usd == 0.75
    assert s.fork_aggregate_budget_usd == 2.5
