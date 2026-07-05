from __future__ import annotations

import os

# Tests must never trace to Logfire (env leakage from a developer's .env) —
# same rule as agent-web's conftest. setup_observability() is then a no-op.
os.environ.pop("LOGFIRE_TOKEN", None)
