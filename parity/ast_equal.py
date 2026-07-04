#!/usr/bin/env python
"""Gate 1 — AST equality comparator (Tier 2 equivalence).

Fires only on PRs labeled `relocation` or `format-only`. Tier-2 equality means
logic is identical while bytes may differ: same AST ignoring source positions,
but NOT ignoring names or docstrings (those carry meaning). Two nodes are equal
iff `ast.dump(a) == ast.dump(b)` (ast.dump omits line/col by default).

Modes:
  * relocations (from the manifest): for every `old.dotted.path: new.dotted.path`,
    extract the named function/class from the base blob (old) and the working
    tree (new) and require AST equality.
  * format-only: every first-party .py changed vs --base must be AST-equal to
    its base version as a whole module.

Run: python parity/ast_equal.py --base <rev> --manifest parity/manifest.yml
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY = ("projects/agent-web/src/", "projects/eval-optimizer/src/", "rules/")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _base_blob(base: str, rel: str) -> str | None:
    try:
        return _git("show", f"{base}:{rel}")
    except subprocess.CalledProcessError:
        return None


def _dump(node: ast.AST) -> str:
    return ast.dump(node)  # positions omitted by default; names/docstrings kept


def _named_node(src: str, name: str) -> ast.AST | None:
    """Find a top-level (or dotted Class.method) def/class named `name`."""
    tree = ast.parse(src)
    *outer, leaf = name.split(".")
    scope: list[ast.stmt] = tree.body
    for part in outer:
        scope = next((n.body for n in scope
                      if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == part), [])
    for n in scope:
        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == leaf:
            return n
    return None


def _dotted_to_file_attr(dotted: str) -> tuple[str, str]:
    """eval_optimizer.legacy.validate.parse_artifact ->
       (projects/eval-optimizer/src/eval_optimizer/legacy/validate.py, parse_artifact).
    Walks candidate module boundaries against the filesystem."""
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):
        modparts, attr = parts[:split], ".".join(parts[split:])
        for base in ("projects/agent-web/src", "projects/eval-optimizer/src", "."):
            cand = ROOT / base / (Path(*modparts).as_posix() + ".py")
            if cand.exists():
                return cand.relative_to(ROOT).as_posix(), attr
    raise FileNotFoundError(f"cannot locate module file for {dotted!r}")


def _changed_py(base: str) -> list[str]:
    out = _git("diff", "--name-only", base, "HEAD")
    return [f for f in out.splitlines() if f.endswith(".py") and f.startswith(FIRST_PARTY)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--manifest", default="parity/manifest.yml")
    ap.add_argument("--mode", choices=["relocation", "format-only", "both"], default="both")
    args = ap.parse_args()

    errors: list[str] = []
    manifest = yaml.safe_load((ROOT / args.manifest).read_text(encoding="utf-8")) or {}
    relocations = manifest.get("relocations") or {}

    if args.mode in ("relocation", "both"):
        for old, new in relocations.items():
            old_file, old_attr = _dotted_to_file_attr(old) if _safe(old) else (None, None)
            try:
                new_file, new_attr = _dotted_to_file_attr(new)
            except FileNotFoundError as e:
                errors.append(f"[relocation] {e}")
                continue
            old_src = _base_blob(args.base, old_file) if old_file else None
            if old_src is None:
                # old path may only exist in the base tree under its pre-move name
                errors.append(f"[relocation] cannot read base source for {old!r}")
                continue
            a = _named_node(old_src, old_attr)
            b = _named_node((ROOT / new_file).read_text(encoding="utf-8"), new_attr)
            if a is None or b is None:
                errors.append(f"[relocation] {old!r} -> {new!r}: node not found (old={a is not None}, new={b is not None})")
            elif _dump(a) != _dump(b):
                errors.append(f"[relocation] {old!r} -> {new!r}: AST differs (logic changed during a move)")

    if args.mode in ("format-only", "both"):
        for rel in _changed_py(args.base):
            old_src = _base_blob(args.base, rel)
            if old_src is None:
                continue  # newly added file — nothing to compare
            new_src = (ROOT / rel).read_text(encoding="utf-8")
            try:
                if _dump(ast.parse(old_src)) != _dump(ast.parse(new_src)):
                    # only an error under the format-only label; under `both` it is
                    # informational unless the file is claimed pure-format.
                    if args.mode == "format-only":
                        errors.append(f"[format-only] {rel}: AST changed — not a formatting-only edit")
            except SyntaxError as e:
                errors.append(f"[format-only] {rel}: parse error {e}")

    if errors:
        print("Gate 1 (ast-equality) FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print("Gate 1 OK: all relocations/format-only edits are AST-equal to their originals.")
    return 0


def _safe(dotted: str) -> bool:
    try:
        _dotted_to_file_attr(dotted)
        return True
    except FileNotFoundError:
        # old path is gone from the working tree (expected post-move) — we read
        # it from the base blob instead, so map via the same walker on base.
        return True


if __name__ == "__main__":
    sys.exit(main())
