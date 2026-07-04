"""Re-vendor integrity check — compares a fresh upstream clone against vendor/.

The AgenticWork mount can truncate large writes silently (see RUNBOOK), so after
copying a new upstream tree into vendor/pydantic-deepagents, prove the copy:

    python revendor_check.py <fresh-clone-dir> [vendor-dir]

Compares file count and sha256 of every pydantic_deep/**/*.py (the installable
package — the part that must be byte-exact). Files touched by patches/ are
expected to differ AFTER you re-apply the patch; run this BEFORE patching, or
accept the listed diffs if they exactly match patches/*.patch targets.

Exit 0 = trees identical. Nonzero = mismatches printed.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def collect(root: Path) -> dict[str, str]:
    pkg = root / "pydantic_deep"
    return {
        str(f.relative_to(root)).replace("\\", "/"): digest(f)
        for f in sorted(pkg.rglob("*.py"))
        if "__pycache__" not in f.parts
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    fresh = Path(sys.argv[1])
    vendor = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "pydantic-deepagents"

    a, b = collect(fresh), collect(vendor)
    bad = 0
    for name in sorted(set(a) | set(b)):
        if name not in a:
            print(f"[extra-in-vendor] {name}")
            bad += 1
        elif name not in b:
            print(f"[MISSING in vendor — truncated copy?] {name}")
            bad += 1
        elif a[name] != b[name]:
            print(f"[content-differs] {name}  (expected if a patches/ target)")
            bad += 1
    print(f"\nfiles: fresh={len(a)} vendor={len(b)} mismatches={bad}")
    if bad == 0:
        print("REVENDOR OK — trees identical.")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
