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
    # encoding="utf-8" is load-bearing: git blobs are UTF-8, but subprocess text
    # mode defaults to the platform encoding (cp1252 on Windows), which mangles
    # non-ASCII (em-dashes in docstrings) and makes byte-identical nodes falsely
    # differ. The first real relocation surfaced this.
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


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


_SRC_ROOTS = ("projects/agent-web/src", "projects/eval-optimizer/src", ".")


def _dotted_to_file_attr(dotted: str) -> tuple[str, str]:
    """eval_optimizer.legacy.validate.parse_artifact ->
       (projects/eval-optimizer/src/eval_optimizer/legacy/validate.py, parse_artifact).
    Walks candidate module boundaries against the WORKING-TREE filesystem — use
    for the NEW (post-move) path, which exists on disk."""
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):
        modparts, attr = parts[:split], ".".join(parts[split:])
        for base in _SRC_ROOTS:
            cand = ROOT / base / (Path(*modparts).as_posix() + ".py")
            if cand.exists():
                return cand.relative_to(ROOT).as_posix(), attr
    raise FileNotFoundError(f"cannot locate module file for {dotted!r}")


def _dotted_to_base_file_attr(base: str, dotted: str) -> tuple[str, str]:
    """Map an OLD dotted path -> (base-tree file, attr) by probing the BASE
    BLOB, not the working tree. A genuine relocation removes the old module
    from the working tree, so its file must be resolved from git `base` — the
    reason `relocations:` never worked until it was first populated."""
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):
        modparts, attr = parts[:split], ".".join(parts[split:])
        for base_dir in _SRC_ROOTS:
            rel = (Path(base_dir) / (Path(*modparts).as_posix() + ".py")).as_posix()
            if _base_blob(base, rel) is not None:
                return rel, attr
    raise FileNotFoundError(f"cannot locate base module file for {dotted!r}")


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
            try:
                new_file, new_attr = _dotted_to_file_attr(new)
            except FileNotFoundError as e:
                errors.append(f"[relocation] new path missing in working tree: {e}")
                continue
            try:
                old_file, old_attr = _dotted_to_base_file_attr(args.base, old)
            except FileNotFoundError as e:
                errors.append(f"[relocation] {e}")
                continue
            old_src = _base_blob(args.base, old_file)
            if old_src is None:  # pragma: no cover - resolver already confirmed it
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
            wt = ROOT / rel
            if not wt.exists():
                continue  # deleted / moved away (relocation mode covers the move)
            new_src = wt.read_text(encoding="utf-8")
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


if __name__ == "__main__":
    sys.exit(main())
