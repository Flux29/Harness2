"""Optional observability via Pydantic Logfire (OpenTelemetry under the hood).

No-op unless ``LOGFIRE_TOKEN`` is set, so it never interferes with runs. When
enabled it traces pydantic-ai/pydantic-deep agent runs, tool calls, token usage,
and pydantic-graph node spans.

Cloud setup: sign up at https://logfire.pydantic.dev, create a project, copy a
write token into `.env` as LOGFIRE_TOKEN. To send to a self-hosted OTel collector
instead, leave LOGFIRE_TOKEN unset and configure OTEL_EXPORTER_OTLP_ENDPOINT
(Logfire respects standard OTel env vars).
"""
from __future__ import annotations

import os

_configured = False


def setup_observability(service_name: str = "eval-optimizer") -> bool:
    """Enable Logfire if LOGFIRE_TOKEN is set. Returns True if instrumentation
    was activated. Safe to call multiple times."""
    global _configured
    if _configured:
        return True
    if not os.environ.get("LOGFIRE_TOKEN", "").strip():
        return False
    try:
        import logfire
    except ImportError:
        print("observability: `logfire` not installed — run `uv sync`. Skipping.")
        return False

    logfire.configure(service_name=service_name)  # reads LOGFIRE_TOKEN from env
    logfire.instrument_pydantic_ai()              # agents, tools, tokens (covers pydantic-deep)
    try:
        logfire.instrument_httpx()                # raw HTTP to OpenRouter / Ollama
    except Exception:
        pass
    _configured = True
    print(f"observability: Logfire enabled (service={service_name})")
    return True
