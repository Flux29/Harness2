from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import os

# Tests must never trace to Logfire (env leakage from a developer's .env) —
# same lesson as eval-optimizer's test_settings_defaults.
os.environ.pop("LOGFIRE_TOKEN", None)
