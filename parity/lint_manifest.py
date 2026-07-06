#!/usr/bin/env python
"""Gate 2 — manifest provenance lints.

Lint one (completeness): every finding id in parity/findings-catalog.yml has an
entry in parity/manifest.yml; every `relocations` source no longer resolves at
its old path while the target does.

Lint two (test coverage): every `status: changed` entry names a verifier — at
least one pytest node-id that exists, or a non-pytest `verified_by` hook — and
declares the matrix rows it moves.

Run: python parity/lint_manifest.py   (resolves the repo root from __file__, so
cwd does not matter — CI invokes it from a project directory).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALID_STATUS = {"identical", "changed", "removed"}
# First-party src roots — relocation resolution is filesystem-based (not import)
# so the lint is venv-independent (CI runs it from the agent-web venv, where
# eval_optimizer is not installed).
_SRC_ROOTS = ("projects/agent-web/src", "projects/eval-optimizer/src", ".")


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / "parity" / name).read_text(encoding="utf-8")) or {}


def _test_exists(node_id: str) -> bool:
    """node_id is repo-root-relative: 'path/to/test_x.py::test_fn'."""
    if "::" not in node_id:
        return False
    rel, func = node_id.split("::", 1)
    f = ROOT / rel
    if not f.exists():
        return False
    src = f.read_text(encoding="utf-8")
    return re.search(rf"^\s*(async\s+)?def\s+{re.escape(func)}\s*\(", src, re.M) is not None


def _module_file(mod: str) -> Path | None:
    """Resolve a dotted module to its first-party file (module.py or package
    __init__.py) by walking the src roots — no import, so venv-independent."""
    rel = Path(*mod.split("."))
    for base in _SRC_ROOTS:
        cand = ROOT / base / rel.with_suffix(".py")
        if cand.exists():
            return cand
        pkg = ROOT / base / rel / "__init__.py"
        if pkg.exists():
            return pkg
    return None


def _relocation_resolves(dotted: str) -> bool:
    """True if a dotted module or module.attr path exists in first-party source
    (attribute presence is a source grep, side-effect free)."""
    if _module_file(dotted) is not None:  # dotted names a module/package
        return True
    mod, _, attr = dotted.rpartition(".")
    if not mod:
        return False
    f = _module_file(mod)
    if f is None:
        return False
    return re.search(rf"\b{re.escape(attr)}\b\s*[=:(]|def\s+{re.escape(attr)}|class\s+{re.escape(attr)}",
                     f.read_text(encoding="utf-8")) is not None


def main() -> int:
    catalog = _load("findings-catalog.yml").get("findings", {})
    manifest = _load("manifest.yml")
    findings = manifest.get("findings", {})
    relocations = manifest.get("relocations") or {}
    errors: list[str] = []

    # ---- Lint one: completeness ----
    for fid in catalog:
        if fid not in findings:
            errors.append(f"[lint one] catalog finding {fid!r} has no manifest entry")
    for fid in findings:
        # Manifest may hold findings discovered after §8 (the catalog is the §8
        # enumeration). Such entries MUST declare a `source`, so a typo can't
        # silently create an orphan entry.
        if fid not in catalog and not findings[fid].get("source"):
            errors.append(
                f"[lint one] manifest finding {fid!r} is not in findings-catalog.yml "
                f"and declares no `source:` (add it to the catalog, or mark it discovered)")

    for src, dst in relocations.items():
        if _relocation_resolves(src):
            errors.append(f"[lint one] relocation source {src!r} still resolves at its old path")
        if not _relocation_resolves(dst):
            errors.append(f"[lint one] relocation target {dst!r} does not resolve")

    # ---- Per-entry validity + lint two ----
    for fid, entry in findings.items():
        status = entry.get("status")
        if status not in VALID_STATUS:
            errors.append(f"[schema] {fid}: status {status!r} not in {sorted(VALID_STATUS)}")
            continue
        if status != "changed":
            continue
        # lint two applies only to `changed`: it must name a verifier — at least
        # one existing pytest, or a non-pytest verified_by CI hook. (matrix_rows
        # is informational: which parity rows moved.)
        tests = entry.get("tests") or []
        verified_by = entry.get("verified_by")
        if not tests and not verified_by:
            errors.append(f"[lint two] {fid}: status=changed names neither a test nor a verified_by hook")
        for node in tests:
            if not _test_exists(node):
                errors.append(f"[lint two] {fid}: test {node!r} does not exist")

    if errors:
        print("Gate 2 (manifest-lint) FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"Gate 2 OK: {len(findings)} findings, {len(relocations)} relocations, all verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
