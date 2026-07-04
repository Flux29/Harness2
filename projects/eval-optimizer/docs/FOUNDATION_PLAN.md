# Foundation Hardening Plan (v2) — quality-first rebuild

**Why:** before bootstrapping the five agents, the core engine must be solid.
This plan addresses four requests, in order, each gated by an exit test:

1. Fix the memory "duplicate recall" issue (de-duplicate on write).
2. Rebuild the linear evaluator-optimizer into the **Planner → Tree-of-Generators
   → Debate-Critics** architecture from the project's design schema.
3. Use **pydantic-graph** as the orchestration substrate (typed nodes, durable
   resumable state).
4. Pilot the **memory** agent via structured-spec output, then batch the rest.

Reasoning budget per role (from the schema, mapped to pydantic-deep `thinking=`):
Planner **high** · Generators **low–medium** · Critics **high**. This minimizes
token waste and "generator drift."

---

## Workstream A — Memory de-duplication (small, do first)

**Root cause (not a search bug):** `memory_check` re-inserts the same three
sentences each run, and `store_memory` has no uniqueness guard, so identical text
produces identical vectors → identical-distance duplicate hits. The first run
looked clean only because nothing was duplicated yet.

**Fix:**
- Migration `infra/initdb/02_dedup.sql` (and a manual-apply note, since initdb
  only runs on a fresh volume): add `content_sha256 TEXT` + a `UNIQUE` index per
  `memory_<agent>.memories`.
- `memory_pg.store_memory`: compute `sha256(content)`, insert with
  `ON CONFLICT (content_sha256) DO NOTHING RETURNING id`; if no row returned,
  fetch and return the existing id. No duplicate vectors ever stored.
- `memory_check`: make the demo idempotent so re-runs don't grow noise.
- Optional defensive de-dup of search results by `content_sha256`.

**Exit:** run `memory_check` twice → count stays at 3; search returns 3 distinct
rows, no repeated distances.

---

## Workstream B — pydantic-graph orchestration substrate

Replace the hand-rolled `for` loop in `loop.py` with a typed graph. This gives
durable, resumable runs and a clean place to hang the schema's stages.

**State** (`PipelineState`, a dataclass persisted between nodes):
`task`, `plan`, `candidates`, `critiques`, `scores`, `selected`, `iteration`,
`failures`.

**Nodes** (`BaseNode` subclasses, each returns the next node or `End`):
`Plan → Generate → Critique → Rank → Validate`, with `Validate` returning either
`End(result)` or back to `Generate` for **targeted regeneration** (bounded by a
max-iteration count — respects the NVIDIA rate limit).

**Persistence:** snapshot `PipelineState` into `memory_common.agent_state`
(`kind='graph_state'`) after each node; support resume via the graph's
`iter_from_persistence`. The Phase-3 durable-memory work already gives us the
table and helpers.

**New deps:** `pydantic-graph`.

---

## Workstream C — The Planner / Tree-of-Generators / Debate-Critics agents

Implemented as typed Pydantic models + pydantic-deep agents, driven by the graph.

**Models (`schema.py`):**
- `ExecutionPlan` — `{goal, steps[], modules[], functions[]}`. **Immutable** once
  produced; generators may not invent architecture.
- `Candidate` — `{id, approach, artifact, generator}`.
- `Critique` — `{candidate_id, dimension, passed, score, findings[]}`.
- `ScoreMatrix` — weighted per-dimension scores → ranked candidates.
- `AgentSpec` — (Workstream D) `{name, role, system_prompt, tools[], memory_schema}`.

**Agents:**
- **Planner** (`thinking="high"`) → emits `ExecutionPlan`.
- **Generators** (`thinking="low"`/`"medium"`) → beam width **3** diverse
  candidates, each varying approach (algorithm / library / data structure). Run
  in parallel (asyncio gather / subagents). Sub-variants optional later.
- **Debate Critics** (`thinking="high"`) — three: **Correctness** (plan
  compliance, edge cases), **Architecture** (file org, dependency hygiene, no
  out-of-plan deps), **Performance** (complexity, memory, scalability). Each
  returns a structured `Critique`; a `Rank` step aggregates a weighted
  `ScoreMatrix` and selects the top candidate. (A lightweight "debate" pass —
  critics see each other's findings before final scores — can be added once the
  base path works.)

**Validation (`Validate` node):** syntax check → static analysis (ruff/pyright)
→ unit tests → runtime execution **inside the pydantic-deep Docker sandbox**.
Failure triggers targeted regeneration of the weakest dimension, not a full
restart.

---

## Workstream D — Pilot: the `memory` agent via structured spec

Once B+C are green on a throwaway coding task:
- Point the pipeline at producing an `AgentSpec` (role, system prompt, tool list,
  memory schema) for the **memory** agent — structured data, not raw code.
- `factory.py` instantiates a real `create_deep_agent` from the `AgentSpec`.
- **Exit:** the generated memory agent loads, and can store + recall via the
  Phase-3 `memory_pg` layer.
- Then batch the other four (query, ingestion, evaluation, system).

---

## Sequencing & module plan

A → B → C → D, each gated. Files:

| Workstream | Files |
|---|---|
| A | `infra/initdb/02_dedup.sql`, `src/eval_optimizer/memory_pg.py`, `memory_check.py` |
| B | `src/eval_optimizer/graph.py`, `pyproject.toml` (+pydantic-graph) |
| C | `src/eval_optimizer/schema.py`, `agents.py` (planner/generators/critics) |
| D | `src/eval_optimizer/factory.py`, agent spec inputs |

`loop.py` is kept as the simple reference path (still works) until the graph
replaces it, so we never lose a green baseline.

---

## Risks & mitigations

- **Call volume.** Tree-of-generators (×3) plus three critics multiplies LLM
  calls per task against the ~40 req/min free tier. Mitigate: beam width 3, cap
  critics at 3, bounded regen, cache. **Option:** run the *low-reasoning
  generators* on a local Ollama LLM (free, no limit) and reserve GLM 5.1 for the
  high-reasoning Planner + Critics. Decide after measuring.
- **Running generated code.** The `Validate` runtime step must execute in the
  Docker sandbox, never the host.
- **Embedding lock.** Dedup adds a column, not a vector change — `VECTOR(1024)`
  and the mxbai-embed-large pin are untouched.
