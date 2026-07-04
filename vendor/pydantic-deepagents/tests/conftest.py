"""Pytest configuration and fixtures."""

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai_backends import LocalBackend, StateBackend

from pydantic_deep.deps import DeepAgentDeps


@pytest.fixture(autouse=True)
def mock_update_check():
    """Skip PyPI version checks in all tests to avoid network calls."""
    with patch("apps.cli.update.check_for_update", return_value=None):
        yield


@pytest.fixture(autouse=True)
def isolate_cli_config(tmp_path: Path) -> Generator[None, None, None]:
    """Point CLI config to a non-existent temp path so tests are isolated from the real
    .pydantic-deep/config.toml in the project directory.  load_config() returns CliConfig()
    defaults when the path does not exist."""
    with patch("apps.cli.config.DEFAULT_CONFIG_PATH", tmp_path / "config.toml"):
        yield


@pytest.fixture(autouse=True)
def mock_subagent_agent():
    """Mock the Agent class in subagents_pydantic_ai to avoid needing API keys."""
    mock_agent = MagicMock()
    with patch("subagents_pydantic_ai.toolset.Agent", return_value=mock_agent):
        yield mock_agent


@pytest.fixture
def state_backend():
    """Create a fresh StateBackend."""
    return StateBackend()


@pytest.fixture
def deps(state_backend):
    """Create default DeepAgentDeps with StateBackend."""
    return DeepAgentDeps(backend=state_backend)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def local_backend(temp_dir):
    """Create a LocalBackend with temporary directory."""
    return LocalBackend(temp_dir)
