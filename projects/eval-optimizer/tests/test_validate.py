"""Offline tests for the artifact parser (no Docker, no network)."""
from __future__ import annotations

from eval_optimizer.validate import parse_artifact

ARTIFACT = '''\
All done. Here is the implementation:

# === pkg/mod.py ===
```python
def add(a, b):
    return a + b
```

# === test_mod.py ===
```python
from pkg.mod import add


def test_add():
    assert add(2, 3) == 5
```
'''


def test_parses_both_files():
    files = parse_artifact(ARTIFACT)
    assert set(files) == {"pkg/mod.py", "test_mod.py"}


def test_strips_prose_and_fences():
    files = parse_artifact(ARTIFACT)
    assert files["pkg/mod.py"].startswith("def add(a, b):")
    assert "```" not in files["pkg/mod.py"]
    assert "All done" not in files["pkg/mod.py"]
    assert files["test_mod.py"].rstrip().endswith("assert add(2, 3) == 5")


def test_no_markers_returns_empty():
    assert parse_artifact("just prose, no markers") == {}
