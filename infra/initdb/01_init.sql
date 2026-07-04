-- AgenticWork — database bootstrap (runs once on first container start).
--
-- Embedding dimension is FIXED at 1024 to match the pinned local embed model
-- (mxbai-embed-large or bge-m3, both 1024-dim). Changing the embed model later
-- to a different dimension requires a migration + full re-embed. Do not change
-- VECTOR(1024) casually.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- digest() for content hashing / backfills

-- ---------------------------------------------------------------------------
-- Shared, cross-agent orchestration state (todos, progress, verdicts, failures)
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS memory_common;

CREATE TABLE IF NOT EXISTS memory_common.agent_state (
    id          TEXT PRIMARY KEY,                 -- 'project:task_id'
    agent       TEXT NOT NULL,                    -- which agent wrote this row
    kind        TEXT NOT NULL,                    -- 'todo' | 'progress' | 'verdict' | 'failure_log'
    data        JSONB NOT NULL,
    embedding   VECTOR(1024),                     -- nullable; only on semantically-searched rows
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_state_kind_idx  ON memory_common.agent_state (kind);
CREATE INDEX IF NOT EXISTS agent_state_agent_idx ON memory_common.agent_state (agent);
CREATE INDEX IF NOT EXISTS agent_state_data_gin  ON memory_common.agent_state USING gin (data jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- Per-agent semantic memory. One schema per agent = hard logical separation,
-- single database, single backup. Phase 1/2 agents first; the five
-- general-purpose agents are pre-created so Phase 4 has somewhere to write.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    agent_name TEXT;
    agents TEXT[] := ARRAY[
        'optimizer', 'evaluator',                          -- Phase 1/2 core pair
        'memory', 'query', 'ingestion', 'evaluation', 'system'  -- Phase 4 general-purpose roster
    ];
BEGIN
    FOREACH agent_name IN ARRAY agents LOOP
        EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I;', 'memory_' || agent_name);

        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS %I.memories (
                id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                content         TEXT NOT NULL,
                content_sha256  TEXT NOT NULL,
                metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding       VECTOR(1024),
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        $f$, 'memory_' || agent_name);

        -- De-dup guard: identical content can never be stored twice.
        EXECUTE format(
            'CREATE UNIQUE INDEX IF NOT EXISTS %I ON %I.memories (content_sha256);',
            agent_name || '_memories_sha_uidx',
            'memory_' || agent_name
        );

        -- HNSW index for cosine similarity search (no training step; fine on an
        -- empty table, unlike IVFFlat).
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I.memories USING hnsw (embedding vector_cosine_ops);',
            agent_name || '_memories_embedding_idx',
            'memory_' || agent_name
        );
    END LOOP;
END $$;
