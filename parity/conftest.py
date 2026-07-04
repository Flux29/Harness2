"""Parity harness (Gate 3) — shared fixtures.

These tests assert that the CURRENT code's observable behavior equals the
committed v1 baselines under baseline/, EXCEPT where a step deliberately flips a
Parity Matrix row. A flip is expressed by editing the specific assertion in this
harness (moving it off `== baseline` to the new expected value with a step
citation) in the SAME commit that changes the behavior; the manifest entry flips
in lockstep (Gate 2). An unexplained diff fails CI.

Runs under the agent-web venv (the CI `parity` job). The eval-optimizer Matrix B
check lives in that project's own test suite, where eval_optimizer is importable.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import CODE_DEFAULT_ENV  # noqa: E402


def load_baseline(rel: str) -> dict:
    return json.loads((BASELINE / rel).read_text(encoding="utf-8"))


@pytest.fixture
def baseline():
    return load_baseline


@pytest.fixture
def code_default_settings(monkeypatch):
    """A Settings() built with the deployment .env neutralized to code defaults,
    matching how the baseline was captured (parity/_env.py)."""
    for k, v in CODE_DEFAULT_ENV.items():
        monkeypatch.setenv(k, v)
    import agent_web.settings as settings_mod
    importlib.reload(settings_mod)
    s = settings_mod.Settings()
    yield s
    importlib.reload(settings_mod)  # restore module-level defaults for other tests
