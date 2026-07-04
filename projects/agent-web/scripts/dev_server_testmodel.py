"""Offline dev server: the full app on TestModel (no keys, no network).

    uv run python scripts/dev_server_testmodel.py   # port 8000
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn
from pydantic_ai.models.test import TestModel

from agent_web.app import create_app
from agent_web.settings import Settings

app = create_app(
    settings=Settings(web_tools=False, mcp_enable=()),
    model=TestModel(call_tools=[]),
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
