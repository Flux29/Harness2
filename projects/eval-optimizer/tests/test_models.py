"""Phase 4.1 (crit-nvidia-coupling, ADR-0003) — provider credentials are
validated lazily, per the provider the resolved model actually selects.
Offline: models are constructed, never called."""
from __future__ import annotations

import pytest

from eval_optimizer.config import Settings
from eval_optimizer.models import build_model

_PROVIDER_VARS = ("NVIDIA_API_KEY", "OPENROUTER_API_KEY")


def _env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for var in _PROVIDER_VARS:
        monkeypatch.delenv(var, raising=False)
    for var, val in values.items():
        monkeypatch.setenv(var, val)


def test_openrouter_only_env_constructs_settings_and_model(monkeypatch):
    _env(monkeypatch, OPENROUTER_API_KEY="sk-or-test")
    s = Settings.from_env()  # must NOT raise on the missing NVIDIA key
    model = build_model("openrouter:z-ai/glm-5.2", settings=s)
    assert type(model).__name__ == "OpenRouterModel"


def test_nvidia_only_env_constructs_settings_and_model(monkeypatch):
    _env(monkeypatch, NVIDIA_API_KEY="nvapi-test")
    s = Settings.from_env()
    model = build_model("z-ai/glm-5.2", settings=s)  # bare id -> NVIDIA endpoint
    assert model is not None and not isinstance(model, str)


def test_missing_openrouter_key_raises_naming_provider(monkeypatch):
    """v1 silently built an OpenRouter model with an empty key; the failure then
    surfaced as an opaque 401 at call time. Now it raises at build time."""
    _env(monkeypatch, NVIDIA_API_KEY="nvapi-test")
    s = Settings.from_env()
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY.*OpenRouter"):
        build_model("openrouter:z-ai/glm-5.2", settings=s)


def test_missing_nvidia_key_raises_naming_provider(monkeypatch):
    _env(monkeypatch, OPENROUTER_API_KEY="sk-or-test")
    s = Settings.from_env()
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY.*NVIDIA"):
        build_model("z-ai/glm-5.2", settings=s)


def test_passthrough_and_ollama_need_no_local_keys(monkeypatch):
    _env(monkeypatch)  # no provider keys at all
    s = Settings.from_env()
    assert build_model("anthropic:claude-fable-5", settings=s) == "anthropic:claude-fable-5"
    assert build_model("ollama:mxbai-embed-large", settings=s) is not None
