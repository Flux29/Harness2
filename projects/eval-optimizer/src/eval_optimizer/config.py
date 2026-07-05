"""Environment-driven settings. All secrets come from .env / the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # load .env if present; real env vars still win


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str
    nvidia_base_url: str
    glm_model: str
    ollama_base_url: str
    embed_model: str
    embed_dim: int
    database_url: str
    # Per-role models (default to GLM; override e.g. PLANNER_MODEL=openrouter:z-ai/glm-5.2)
    planner_model: str
    generator_model: str
    critic_model: str
    # OpenRouter (OpenAI-compatible) — used for model ids prefixed "openrouter:"
    openrouter_api_key: str
    openrouter_base_url: str
    # Fork configuration (ADR-0011), centralized here (Phase 3.5). Defaults
    # preserve forking.py's previous hardcoded values.
    fork_max_branches: int
    fork_test_command: str
    fork_test_timeout_s: float
    fork_per_branch_budget_usd: float
    fork_aggregate_budget_usd: float

    @classmethod
    def from_env(cls) -> "Settings":
        # Provider credentials are validated lazily in models.build_model() for
        # the provider actually selected (Phase 4.1, ADR-0003): an OpenRouter-only
        # env must not fail on a missing NVIDIA key, and vice versa.
        glm = os.environ.get("GLM_MODEL", "z-ai/glm-5.2")
        return cls(
            nvidia_api_key=os.environ.get("NVIDIA_API_KEY", "").strip(),
            nvidia_base_url=os.environ.get(
                "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
            ),
            glm_model=glm,
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11435"),
            embed_model=os.environ.get("EMBED_MODEL", "mxbai-embed-large"),
            embed_dim=int(os.environ.get("EMBED_DIM", "1024")),
            database_url=os.environ.get(
                "DATABASE_URL", "postgresql://agentic:agentic@localhost:5433/agentic"
            ),
            planner_model=os.environ.get("PLANNER_MODEL", glm),
            generator_model=os.environ.get("GENERATOR_MODEL", glm),
            critic_model=os.environ.get("CRITIC_MODEL", glm),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            fork_max_branches=int(os.environ.get("FORK_MAX_BRANCHES", "8")),
            fork_test_command=os.environ.get("FORK_TEST_COMMAND", "pytest -q"),
            fork_test_timeout_s=float(os.environ.get("FORK_TEST_TIMEOUT_S", "90")),
            fork_per_branch_budget_usd=float(os.environ.get("FORK_PER_BRANCH_BUDGET_USD", "0.75")),
            fork_aggregate_budget_usd=float(os.environ.get("FORK_AGGREGATE_BUDGET_USD", "2.5")),
        )
