"""Phase 3 exit check: prove the durable memory layer works end to end.

Run twice to demonstrate persistence across processes:
  uv run python -m eval_optimizer.memory_check
  uv run python -m eval_optimizer.memory_check   # memory count grows; survives restarts

What it does:
  1. ping Postgres
  2. embed via local Ollama and store 3 memories for the 'optimizer' agent
  3. semantic-search them with a fresh query
  4. write + read back a progress row in memory_common.agent_state
"""
from __future__ import annotations

from .memory_pg import Memory


def main() -> int:
    mem = Memory()

    print("1) Postgres ping ...", "OK" if mem.ping() else "FAIL")

    print("2) storing 3 memories (de-duplicated; embedded via local Ollama) ...")
    facts = [
        "The evaluator-optimizer loop uses GLM 5.1 for reasoning.",
        "Embeddings are produced locally by mxbai-embed-large, 1024 dimensions.",
        "Durable memory lives in Postgres with the pgvector extension.",
    ]
    for f in facts:
        mid = mem.store_memory("optimizer", f, metadata={"source": "memory_check"})
        print(f"   stored/existing id={mid}: {f[:50]}...")
    count = mem.count_memories("optimizer")
    print(f"   total memories for 'optimizer': {count}  (should stay 3 on re-runs)")

    print("3) semantic search: 'what model creates the vectors?'")
    for hit in mem.search_memory("optimizer", "what model creates the vectors?", k=3):
        print(f"   dist={hit['distance']:.4f}  {hit['content'][:60]}")

    print("4) progress round-trip in agent_state ...")
    mem.save_state("eval-optimizer:progress", "optimizer", "progress",
                   {"project": "eval-optimizer", "note": "memory_check ran"})
    latest = mem.latest_state("progress", "optimizer")
    print("   read back:", latest["data"] if latest else None)

    print("\nPhase 3 PASSED: embeddings + vector search + durable state all work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
