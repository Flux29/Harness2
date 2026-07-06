"""The pip guard denies its documented bypasses and passes the uv workflow.

ADR-0022 (crit-pip-hook): the matcher decides from parsed argv, so the
critique's bypass — an allow-hint substring smuggled in a comment — must deny,
and legitimate uv-managed commands must pass.
"""

import importlib.util
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[3] / "rules" / "hooks" / "agentic_pre_tool_use.py"
_spec = importlib.util.spec_from_file_location("agentic_pre_tool_use", _HOOK)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

DENIED = [
    "pip install requests",
    "pip install requests  # .venv",  # the critique's comment-smuggled waiver
    "pip install requests && echo conda",  # allow-hint after a separator
    "echo ready; pip install requests",  # deny in any segment, not just the first
    "pip3 install requests",
    "python -m pip install requests",
    "python3 -m pip install requests",
    "py -3.12 -m pip install requests",
    r"C:\Python312\python.exe -m pip install requests",  # full-path invocation
    "pip --no-cache-dir install requests",  # options before the subcommand
    'pip install "unterminated',  # unparseable: fallback denies, no waiver
]

ALLOWED = [
    "uv add requests",
    "uv pip install requests",  # uv-managed: the policy-sanctioned pip surface
    "uv run pytest -q",
    "uv sync",
    "pip download requests",  # not an install
    "echo pip install",  # a mention, not an invocation
    "grep -rn 'pip install' docs/",
]


@pytest.mark.parametrize("command", DENIED)
def test_denied(command: str) -> None:
    assert hook._command_denied(command), f"should DENY: {command!r}"


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed(command: str) -> None:
    assert not hook._command_denied(command), f"should ALLOW: {command!r}"
