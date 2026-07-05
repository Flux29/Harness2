"""C5 POC (harness-native, ADR-0011): fork a builder agent across approaches,
let the harness run each branch's tests, and report which branch is viable.

Prereqs: OpenRouter key in the USER env; `pytest` available (dev dep); and —
Phase 5.2 — `EVALOPT_ALLOW_HOST_EXEC=1`. Tests run on the host (LocalBackend),
so that acknowledgment is a required configuration on a machine you trust with
the generated code, not just this docstring's advice.

Run:  uv run python -m eval_optimizer.fork_check          (discards all files)
      uv run python -m eval_optimizer.fork_check --save   (keeps the winner in cache/fork-winner)
"""
from __future__ import annotations

import asyncio
import sys

from .forking import run_forked_viability

TASK = (
    "Build a small Python module `slugify` with a function `slugify(text: str) -> str` "
    "that lowercases, trims, replaces runs of non-alphanumeric chars with single hyphens, "
    "and strips leading/trailing hyphens. Include pytest tests."
)


def main() -> int:
    save_dir = "cache/fork-winner" if "--save" in sys.argv else None
    report = asyncio.run(run_forked_viability(TASK, save_winner_dir=save_dir))

    print(f"\ntask   : {report.task[:70]}...")
    print("branches:")
    for b in report.branches:
        ratio = "n/a" if b.test_pass_ratio is None else f"{b.test_pass_ratio:.2f}"
        flag = "WIN" if b.branch_id == report.winner_branch_id else "   "
        cost = "?" if b.cost_usd is None else f"${b.cost_usd:.3f}"
        print(f"  [{flag}] {b.label:14} tests={ratio}  turns={b.turns}  errs={b.error_count}  cost={cost}")
        if b.preview:
            print(f"          {b.preview[:120]}")
    print(f"\nwinner : {report.winner_branch_id}")
    print(f"any_viable: {report.any_viable}")
    if report.winner_dir:
        print(f"winner files: {report.winner_dir}")

    print("\nC5 PASSED: a branch passed its tests and was merged." if report.any_viable
          else "\nC5: no branch passed tests — plan/model may be non-viable. Inspect above.")
    return 0 if report.any_viable else 1


if __name__ == "__main__":
    raise SystemExit(main())
