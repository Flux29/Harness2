"""Logfire wiring (ADR-0009) — opt-in via LOGFIRE_TOKEN, no-op otherwise."""
from __future__ import annotations

import os


def configure() -> bool:
    if not os.getenv("LOGFIRE_TOKEN"):
        return False
    import logfire

    logfire.configure(service_name="agent-web", send_to_logfire="if-token-present")
    logfire.instrument_pydantic_ai()  # spans for every agent run / model call / tool
    return True
