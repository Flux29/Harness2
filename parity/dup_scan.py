#!/usr/bin/env python
"""Gate 4 — duplication detection.

An AST-hash duplication scan over first-party code. Every function/method body
is normalized (identifier names canonicalized, docstrings and literals folded,
locations stripped) and hashed. Two functions in different locations sharing a
hash are a duplicate cluster.

The gate is monotonic against parity/dup-allowlist.yml: the allowlist may only
shrink. Any cluster not covered by a live allowlist entry fails; any expired
entry fails.

Run:
  python parity/dup_scan.py                          # report clusters
  python parity/dup_scan.py --allowlist parity/dup-allowlist.yml   # enforce
  python parity/dup_scan.py --today YYYY-MM-DD        # for expiry checks in CI
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# First-party code only. Vendor duplicates are outside the blast radius
# (pristine-vendor rule) and stay inventoried-but-exempt.
SCAN_ROOTS = [
    "projects/agent-web/src",
    "projects/eval-optimizer/src",
    "rules",
]
MIN_STATEMENTS = 3  # ignore trivial stubs (pass, single return, re-exports)


class _Normalizer(ast.NodeTransformer):
    """Canonicalize identifiers and fold docstrings/constants so structurally
    identical bodies hash equal regardless of naming."""

    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def _canon(self, name: str) -> str:
        return self._names.setdefault(name, f"v{len(self._names)}")

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id=self._canon(node.id), ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self._canon(node.arg)
        node.annotation = None
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.copy_location(ast.Constant(value="<const>"), node)


def _body_statements(fn: ast.AST) -> list[ast.stmt]:
    body = list(getattr(fn, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]  # drop docstring
    return body


def _hash_fn(fn: ast.AST) -> str | None:
    stmts = _body_statements(fn)
    if len(stmts) < MIN_STATEMENTS:
        return None
    module = ast.Module(body=[s for s in stmts], type_ignores=[])
    normalized = _Normalizer().visit(module)
    ast.fix_missing_locations(normalized)
    dump = ast.dump(normalized, annotate_fields=False)
    return hashlib.sha256(dump.encode()).hexdigest()[:16]


def _scan() -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = {}
    for root in SCAN_ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if {".venv", "__pycache__"} & set(path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    h = _hash_fn(node)
                    if h:
                        loc = f"{path.relative_to(ROOT).as_posix()}::{node.name}"
                        clusters.setdefault(h, []).append(loc)
    return {h: sorted(set(locs)) for h, locs in clusters.items() if len(set(locs)) > 1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allowlist")
    ap.add_argument("--today", help="YYYY-MM-DD for expiry checks (CI passes date)")
    args = ap.parse_args()

    clusters = _scan()

    if not args.allowlist:
        if not clusters:
            print("dup-scan: no first-party duplicate clusters found.")
            return 0
        print(f"dup-scan: {len(clusters)} duplicate cluster(s):")
        for h, locs in sorted(clusters.items()):
            print(f"  {h}: {', '.join(locs)}")
        return 0

    allow = yaml.safe_load((ROOT / args.allowlist).read_text(encoding="utf-8")) or {}
    entries = {e["hash"]: e for e in (allow.get("allow") or [])}
    errors: list[str] = []

    for h, locs in sorted(clusters.items()):
        if h not in entries:
            errors.append(f"NEW duplicate cluster {h} not in allowlist: {', '.join(locs)}")

    for h, e in entries.items():
        if h not in clusters:
            errors.append(f"stale allowlist entry {h} — cluster no longer present (allowlist must shrink; remove it)")
        expires = e.get("expires")
        if expires and args.today and str(expires) < args.today:
            errors.append(f"allowlist entry {h} expired on {expires} (today={args.today})")

    if errors:
        print("Gate 4 (dup-scan) FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"Gate 4 OK: {len(clusters)} cluster(s), all covered by non-expired allowlist entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
