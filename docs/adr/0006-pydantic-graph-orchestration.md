# ADR-0006 — pydantic-graph 2.x as the orchestration substrate

**Status:** Accepted · 2026-06-29 · **Integration DEFERRED by ADR-0021
(2026-07-06):** the `graph.py` pipeline is a working scaffold (real nodes +
ranking matrix, LLM steps stubbed) preserved in committed `eval_optimizer/legacy/`
pending resumption. pydantic-graph stays a project dependency; its determinism /
token-cost / quality goals remain the reason to finish the integration later.

## Context
The Schema.txt architecture (ADR-0005) is a multi-stage state machine with a
bounded feedback loop. A hand-rolled `for`-loop driver works but gives no typed
state, no durable resume, and no structural clarity. We wanted durable,
resumable, typed orchestration — and it should integrate with our Postgres state.

## Decision
Use **pydantic-graph** (ships with pydantic-ai) as the substrate. Nodes are typed
`BaseNode` subclasses (`Plan → Generate → Criticize → Rank → Validate`); state is
a serializable dataclass; the persistence side-channel lives in `deps`.

The installed version is **2.x**, a rewrite with a `GraphBuilder` API. Verified
working recipe (reverse-engineered, since docs were rate-limited):
- register nodes with `builder.add(builder.node(Cls))` — edges are inferred from
  each `run()`'s return type hints;
- declare only the entry edge explicitly: `edge_from(start_node).to(Plan)`;
- `build(validate_graph_structure=False)` — the runtime navigates via the node
  instance each `run()` returns (`End(...)` terminates), so structural validation
  is unnecessary and stricter than we need;
- start the run with `inputs=Plan()`;
- **node class names must not collide with schema model names** (hence the node
  is `Criticize`, the model is `Critique`).

## Consequences
- Typed, inspectable, resumable pipeline; snapshots persist to
  `memory_common.agent_state` (`kind='graph_state'`).
- Pinned to a young 2.x API that may shift — the recipe above is the contract;
  re-verify on upgrades.
- Workstream B runs the graph with deterministic **stub** nodes (no LLM); C4
  swaps the stubs for the real agents.
