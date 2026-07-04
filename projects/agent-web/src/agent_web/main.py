"""Production entrypoint: `uvicorn agent_web.main:app`.

Import-time side effects (real Settings, tracing) live HERE ONLY.
Tests import from agent_web.app instead — no .env leakage.
"""
from .app import create_app

app = create_app()
