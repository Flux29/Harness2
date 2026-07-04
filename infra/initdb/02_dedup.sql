-- Migration: add content de-duplication to existing memories tables.
--
-- initdb scripts only run on a FRESH volume, so apply this by hand to the
-- already-populated 'agentic' database:
--
--   docker exec -i agentic-postgres-1 psql -U agentic -d agentic < 02_dedup.sql
--   (PowerShell:  Get-Content 02_dedup.sql | docker exec -i agentic-postgres-1 psql -U agentic -d agentic)
--
-- Idempotent: safe to run more than once.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
DECLARE
    agent_name  TEXT;
    schema_name TEXT;
    agents TEXT[] := ARRAY[
        'optimizer', 'evaluator', 'memory', 'query', 'ingestion', 'evaluation', 'system'
    ];
BEGIN
    FOREACH agent_name IN ARRAY agents LOOP
        schema_name := 'memory_' || agent_name;

        -- 1. add the hash column if missing
        EXECUTE format(
            'ALTER TABLE %I.memories ADD COLUMN IF NOT EXISTS content_sha256 TEXT;',
            schema_name
        );

        -- 2. backfill hashes for existing rows
        EXECUTE format(
            $q$UPDATE %I.memories
               SET content_sha256 = encode(digest(content, 'sha256'), 'hex')
               WHERE content_sha256 IS NULL;$q$,
            schema_name
        );

        -- 3. drop existing duplicates, keeping the lowest id per identical content
        EXECUTE format(
            $q$DELETE FROM %I.memories a
               USING %I.memories b
               WHERE a.id > b.id
                 AND a.content_sha256 = b.content_sha256;$q$,
            schema_name, schema_name
        );

        -- 4. enforce uniqueness going forward
        EXECUTE format(
            'CREATE UNIQUE INDEX IF NOT EXISTS %I ON %I.memories (content_sha256);',
            agent_name || '_memories_sha_uidx',
            schema_name
        );
    END LOOP;
END $$;
