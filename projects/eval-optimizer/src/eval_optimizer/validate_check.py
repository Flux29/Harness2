"""Standalone check for the sandboxed validator (C4/C5 keystone).

Runs `validate_artifact` on a tiny known-good artifact (a palindrome module +
a passing test), exercising parse -> write -> syntax/ruff/pytest in the sandbox.

Prereq (docker mode, default):  docker build -t evalopt-sandbox infra/sandbox
Run:  uv run python -m eval_optimizer.validate_check
Local (trusted, no docker):  set VALIDATE_MODE=local  (needs ruff + pytest)
"""
from __future__ import annotations

from .validate import validate_artifact

GOOD_ARTIFACT = '''\
Here is the implementation:

# === palindrome.py ===
```python
def is_palindrome(s: str) -> bool:
    cleaned = [c.lower() for c in s if c.isalnum()]
    return cleaned == cleaned[::-1]
```

# === test_palindrome.py ===
```python
from palindrome import is_palindrome


def test_basic():
    assert is_palindrome("A man, a plan, a canal: Panama")
    assert not is_palindrome("hello")
    assert is_palindrome("")
```
'''


def main() -> int:
    result = validate_artifact(GOOD_ARTIFACT)
    print(f"runner : {result.runner}")
    print(f"files  : {result.files_written}")
    for c in result.checks:
        flag = "ok " if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}")
        if not c.passed and c.detail:
            print("        " + c.detail.strip().replace("\n", "\n        ")[:600])
    print(f"tests  : {result.tests_passed}/{result.tests_total}")
    print(f"\nPASSED={result.passed}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
