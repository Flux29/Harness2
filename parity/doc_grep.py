#!/usr/bin/env python
"""Phase 2 exit-gate doc-grep — keep the fixed doc drift from silently returning.

Scans a curated set of LIVING docs for banned stale strings. Deliberately does
NOT scan:
  - docs/adr/**            — decision records legitimately keep glm-5.1/NVIDIA history
  - docs/HarnessRefactor.md, docs/HarnessCritique.md — plan/critique quote the drift
  - HANDOFF.md             — frozen historical record (its :8000 is history)
  - parity/**              — the machinery that *names* the findings
  - catalogs/**, infra compose, .env.example — NVIDIA is a real supported provider

Run: python parity/doc_grep.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIVING_DOCS = [
    "README.md",
    "PDR.md",
    "docs/RUNBOOK-smoke.md",
    "projects/agent-web/README.md",
    "projects/eval-optimizer/README.md",
    "projects/eval-optimizer/AGENTS.md",
    "projects/eval-optimizer/pyproject.toml",
    "infra/README.md",
]

BANS = [
    (re.compile(r"NVIDIA-hosted", re.I), "stale provider claim 'NVIDIA-hosted' (default path is OpenRouter)"),
    (re.compile(r"GLM[\s-]?5\.1", re.I), "stale model version 'GLM 5.1' (decided default is glm-5.2)"),
    (re.compile(r"(?::|port\s+)8000\b"), "stale port 8000 (single-server port is 8801)"),
]


def main() -> int:
    findings: list[str] = []
    for rel in LIVING_DOCS:
        p = ROOT / rel
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for rx, why in BANS:
                if rx.search(line):
                    findings.append(f"{rel}:{i}: {why}\n      | {line.strip()}")

    if findings:
        print("doc-grep FAILED — fixed drift reappeared in a living doc:")
        for f in findings:
            print("  -", f)
        return 1
    print(f"doc-grep OK: {len(LIVING_DOCS)} living docs clean of the banned stale strings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
