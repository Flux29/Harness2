# AgenticWork infra

Minimal stateful-services stack for the agent build: **Postgres (pgvector)** for
durable shared memory and **Ollama** for local embeddings. Kept deliberately
separate from the RAG repo's compose (own project name `agentic`, own network,
volumes, ports, and DB credentials).

## Start

```powershell
cd C:\Users\pollm\AgenticWork\infra
docker compose -p agentic up -d
# GPU (optional, for local LLM inference; embeddings don't need it):
docker compose -p agentic -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Ports (host)

| Service  | Host port | In-container | Why non-standard |
|----------|-----------|--------------|------------------|
| Postgres | **5433**  | 5432         | RAG stack uses 5432 |
| Ollama   | **11435** | 11434        | RAG stack uses 11434 |

Connection string (host): `postgresql://agentic:agentic@localhost:5433/agentic`
Ollama base URL (host): `http://localhost:11435`

## Pull the embedding model (one time)

Dimension is pinned to **1024** in `initdb/01_init.sql`. Use a 1024-dim model:

```powershell
docker exec -it agentic-ollama-1 ollama pull mxbai-embed-large    # English, recommended
# or:  docker exec -it agentic-ollama-1 ollama pull bge-m3         # multilingual, 8192 ctx
```

> If you ever switch to a model with a different dimension, you must change
> `VECTOR(1024)` everywhere and re-embed all stored memories. Avoid.

## What the init SQL creates

- `CREATE EXTENSION vector`
- `memory_common.agent_state` — shared todos / progress / verdicts / failures (JSONB + optional vector)
- One `memory_<agent>` schema per agent (`optimizer`, `evaluator`, plus the five
  general-purpose roles), each with a `memories` table + HNSW cosine index.

Re-running init: the SQL only runs on a **fresh** volume. To re-bootstrap, remove
the volume (`docker compose -p agentic down -v`) — this deletes all stored memory.
