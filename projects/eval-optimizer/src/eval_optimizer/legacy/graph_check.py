"""Workstream B exit check: run the pipeline graph (stub nodes, no LLM) and
persist each node's state snapshot to Postgres (memory_common.agent_state).

Run: `uv run python -m eval_optimizer.graph_check`

Proves: graph wiring, the bounded regen edge firing, and durable graph state.
"""
from __future__ import annotations

import asyncio

from .graph import run_pipeline
from ..memory_pg import Memory
from ..observability import setup_observability


def main() -> int:
    setup_observability()
    mem = Memory()

    def persister(node: str, snap: dict) -> None:
        mem.save_state(f"eval-optimizer:graph:{node}", "optimizer", "graph_state", {"node": node, **snap})
        print(f"  [persist] {node:<18} iter={snap['iteration']} selected={snap['selected']} fails={len(snap['failures'])}")

    print("running pipeline graph (stub nodes) with Postgres persistence ...")
    res = asyncio.run(
        run_pipeline("Build a JSON field parity comparison", persister=persister, max_iterations=3)
    )

    print(f"\nRESULT passed={res.passed} iterations={res.iterations} "
          f"selected={res.selected.id if res.selected else None}")
    print("ranking :", [(r.candidate_id, r.total_score) for r in res.ranking])
    print("failures:", res.failures)

    latest = mem.latest_state("graph_state")
    print("latest graph_state in Postgres:", latest["data"] if latest else None)

    ok = res.passed and res.iterations >= 2  # regen edge must have fired at least once
    print("\nWorkstream B PASSED: graph ran, regen edge fired, state persisted." if ok
          else "\nWorkstream B: unexpected result — check output above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
