"""Model wiring. Per-role, provider-flexible, with transport-level retry.

- 429 / 5xx / network retries (honoring Retry-After) live in a shared httpx
  client at the transport layer (ADR-0008) — covers every call incl. embeddings.
- `build_model()` resolves: ollama: -> local; openrouter: -> native OpenRouter
  provider (so genai-prices can resolve cost); other provider:model -> pydantic-ai
  inference; bare id -> NVIDIA endpoint.

GLM is reached via NVIDIA/OpenRouter for reasoning only; embeddings use Ollama.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import Settings


@lru_cache(maxsize=1)
def _retrying_http_client() -> Any:
    """Shared async httpx client with retry on 429/5xx/network, respecting
    Retry-After then exponential backoff. Replaces the hand-rolled loop."""
    from httpx import AsyncClient, HTTPStatusError
    from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

    from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig, wait_retry_after

    def _validate(response: Any) -> None:
        # Raise (-> retry) only on transient statuses; let other 4xx fail fast.
        if response.status_code in (429, 500, 502, 503, 504):
            response.raise_for_status()

    transport = AsyncTenacityTransport(
        config=RetryConfig(
            retry=retry_if_exception_type(HTTPStatusError),
            wait=wait_retry_after(
                fallback_strategy=wait_exponential(multiplier=1, max=60),
                max_wait=300,
            ),
            stop=stop_after_attempt(6),
            reraise=True,
        ),
        validate_response=_validate,
    )
    return AsyncClient(transport=transport)


def _chat_model_cls() -> Any:
    try:  # pydantic-ai >= ~1.0
        from pydantic_ai.models.openai import OpenAIChatModel as _ChatModel
    except ImportError:  # older
        from pydantic_ai.models.openai import OpenAIModel as _ChatModel  # type: ignore
    return _ChatModel


def _openai_compatible(model_id: str, base_url: str, api_key: str) -> Any:
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=base_url, api_key=api_key, http_client=_retrying_http_client()
    )
    return _chat_model_cls()(model_id, provider=provider)


def _openrouter_model(model_id: str, settings: Settings) -> Any:
    """Native OpenRouter MODEL (not the generic OpenAI parser): handles
    OpenRouter's response shape incl. non-OpenAI finish_reasons (e.g. 'error'),
    resolves cost as `openrouter:<id>`, and uses the retry-aware HTTP client."""
    from pydantic_ai.models.openrouter import OpenRouterModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(
        api_key=settings.openrouter_api_key, http_client=_retrying_http_client()
    )
    return OpenRouterModel(model_id, provider=provider)


def _nvidia_model(model_id: str, settings: Settings) -> Any:
    return _openai_compatible(model_id, settings.nvidia_base_url, settings.nvidia_api_key)


def build_glm_model(settings: Settings | None = None) -> Any:
    """GLM on NVIDIA Build (legacy/fallback path)."""
    settings = settings or Settings.from_env()
    return _nvidia_model(settings.glm_model, settings)


def build_model(model_id: str | None = None, settings: Settings | None = None) -> Any:
    """Resolve a per-role model id to a pydantic-ai model.

    - ``ollama:<name>``      -> LOCAL Ollama (OpenAI-compatible), e.g. embeddings host.
    - ``openrouter:<name>``  -> native OpenRouter provider (e.g. z-ai/glm-5.2).
    - other ``provider:model`` (anthropic:, openai:, ...) -> pydantic-ai inference.
    - bare id (``z-ai/glm-5.2``) -> NVIDIA endpoint.
    """
    settings = settings or Settings.from_env()
    model_id = model_id or settings.glm_model

    if model_id.startswith("ollama:"):
        name = model_id.split(":", 1)[1]
        base = settings.ollama_base_url.rstrip("/") + "/v1"
        return _openai_compatible(name, base, "ollama")

    if model_id.startswith("openrouter:"):
        name = model_id.split(":", 1)[1]  # e.g. z-ai/glm-5.2
        return _openrouter_model(name, settings)

    if ":" in model_id:
        return model_id  # let pydantic-ai resolve the provider (anthropic:, openai:, ...)

    return _nvidia_model(model_id, settings)
