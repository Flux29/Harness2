# ADR-0004 — Durable memory on Postgres + pgvector; local model-locked embeddings

**Status:** Accepted · 2026-06-29

## Context
Agents need durable, queryable, cross-session memory. The harness ships
file-based `MEMORY.md` (fine for a single agent's scratch memory) but not shared,
searchable state. Embeddings are model-locked — vectors from different models
aren't comparable and the model fixes the vector dimension — so the embedder is
the *most* permanent component. Native pgvector on Windows requires an MSVC build.

## Decision
- **Store:** Postgres + pgvector via the official Docker image (`pgvector/pgvector:pg17`).
  One database `agentic`; a shared `memory_common.agent_state` table (JSONB +
  optional vector) plus one `memory_<agent>` schema per agent with a `memories`
  table (HNSW cosine index).
- **Embeddings:** **local Ollama, pinned** to `mxbai-embed-large` (1024 dims →
  `VECTOR(1024)`). No rate limit, private, offline. NVIDIA/cloud is reserved for
  reasoning, never embeddings.
- **De-duplication:** a `content_sha256` unique index + check-before-embed +
  `ON CONFLICT DO NOTHING` (Workstream A) — identical content can never produce a
  duplicate row/vector, and duplicates don't cost an embedding call.

## Consequences
- Single instance to run/back up; hard logical isolation per agent via schemas.
- Changing the embed model later means a full re-embed + a `VECTOR(n)` migration —
  deliberately avoided by pinning up front.
- Vectors are passed as `'[...]'::vector` literals, so no numpy/pgvector-python
  adapter dependency — just `psycopg`.
