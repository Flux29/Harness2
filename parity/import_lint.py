#!/usr/bin/env python
"""Gate 5 — import contract.

Two checks over first-party packages:
  1. Circular-import detection on the first-party import graph.
  2. The declared layer contract in parity/layer-rules.yml.

Static: parses `import`/`from ... import` with ast; never executes the code.

Run: python parity/import_lint.py --rules parity/layer-rules.yml
"""
from __future__ import annotations

import argparse
import ast
import sys
from fnmatch import fnmatch
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _iter_py(root: Path):
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if parts & {".venv", "__pycache__", "node_modules", "vendor"}:
            continue
        yield p


def _module_of(path: Path, roots: list[Path]) -> str | None:
    """Full dotted module name of a first-party file, e.g.
    projects/eval-optimizer/src/eval_optimizer/legacy/agents.py ->
    'eval_optimizer.legacy.agents'. `__init__.py` -> the package itself."""
    for r in roots:
        try:
            rel = path.relative_to(r)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None
    return None


def _imports(path: Path, roots: list[Path]) -> list[str]:
    """Absolute dotted import targets. Relative imports (ADR-0021) are RESOLVED
    to absolute against the file's own module path, so intra-package layer rules
    (live-path-never-imports-legacy) actually see `from .legacy.x import ...`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    mod = _module_of(path, roots)
    pkg_parts = (mod.split(".")[:-1] if mod and not (path.name == "__init__.py")
                 else (mod.split(".") if mod else []))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative — resolve against this file's package
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)] if node.level > 1 else pkg_parts
                tail = node.module.split(".") if node.module else []
                resolved = ".".join([*base, *tail])
                if resolved:
                    out.append(resolved)
            elif node.module:
                out.append(node.module)
    return out


def _top_package(path: Path, roots: list[Path]) -> str | None:
    m = _module_of(path, roots)
    return m.split(".")[0] if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default="parity/layer-rules.yml")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / args.rules).read_text(encoding="utf-8"))
    roots = [ROOT / r for r in cfg["first_party_roots"] if (ROOT / r).exists()]
    rules = cfg.get("rules", [])
    errors: list[str] = []

    # Build the first-party module set and import graph (package granularity).
    files = [p for r in roots for p in _iter_py(r)]
    first_party_pkgs = {pkg for p in files if (pkg := _top_package(p, roots))}
    graph: dict[str, set[str]] = {p: set() for p in first_party_pkgs}

    for path in files:
        src_pkg = _top_package(path, roots)
        src_full = _module_of(path, roots) or ""
        for imp in _imports(path, roots):
            head = imp.split(".")[0]
            if src_pkg and head in first_party_pkgs and head != src_pkg:
                graph[src_pkg].add(head)
            # Layer rules match the full dotted import; source is matched at both
            # top-package and full-module granularity, with an optional
            # `except_from` (full-module) carve-out (ADR-0021: exempt
            # legacy-internal imports from the live-never-imports-legacy rule).
            for rule in rules:
                ff, fi = rule["forbid_from"], rule["forbid_import"]
                from_ok = (ff == "*" or src_pkg == ff or fnmatch(src_pkg or "", ff)
                           or src_full == ff or src_full.startswith(ff + ".") or fnmatch(src_full, ff))
                exc = rule.get("except_from")
                if exc and (fnmatch(src_full, exc) or src_full == exc or src_full.startswith(exc.rstrip("*"))):
                    continue
                imp_ok = imp == fi or imp.startswith(fi + ".") or fnmatch(imp, fi)
                if from_ok and imp_ok:
                    errors.append(
                        f"[layer] {path.relative_to(ROOT)}: "
                        f"{src_full!r} imports {imp!r} — forbidden by {rule['name']!r} ({rule['reason']})"
                    )

    # Cycle detection (DFS) over the package graph.
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def visit(n: str, stack: list[str]) -> None:
        color[n] = GREY
        for m in sorted(graph.get(n, ())):
            if color.get(m, BLACK) == GREY:
                cyc = " -> ".join(stack[stack.index(m):] + [m]) if m in stack else f"{n} -> {m}"
                errors.append(f"[cycle] first-party import cycle: {cyc}")
            elif color.get(m, BLACK) == WHITE:
                visit(m, stack + [m])
        color[n] = BLACK

    for n in sorted(graph):
        if color[n] == WHITE:
            visit(n, [n])

    if errors:
        print("Gate 5 (import-lint) FAILED:")
        for e in sorted(set(errors)):
            print("  -", e)
        return 1
    print(f"Gate 5 OK: {len(first_party_pkgs)} first-party packages, no cycles, "
          f"{len(rules)} layer rules satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
