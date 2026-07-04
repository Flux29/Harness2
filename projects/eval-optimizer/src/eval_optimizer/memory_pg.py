"""Phase 3 durable memory: local Ollama embeddings -> Postgres/pgvector.

Two stores, both in the `agentic` database:
  - per-agent semantic memory:  memory_<agent>.memories
  - shared orchestration state:  memory_common.agent_state

Embeddings come from LOCAL Ollama (mxbai-embed-large, 1024-dim) via Ollama's
OpenAI-compatible endpoint. NVIDIA/GLM is never used for embeddings.

Vectors are passed as `'[...]'::vector` string literals, so no numpy / pgvector
Python adapter is required — just psycopg.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import psycopg
from openai import OpenAI

from .config import Settings

# Agents that have a `memory_<name>` schema (see infra/initdb/01_init.sql).
# Whitelisted because the name is interpolated into a SQL identifier.
KNOWN_AGENTS = frozenset(
    {"optimizer", "evaluator", "memory", "query", "ingestion", "evaluation", "system"}
)


def _schema_for(agent: str) -> str:
    if agent not in KNOWN_AGENTS:
        raise ValueError(f"Unknown agent {agent!r}. Known: {sorted(KNOWN_AGENTS)}")
    return f"memory_{agent}"


def _vec_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class Memory:
    """Thin data-access layer over the agentic Postgres + Ollama embeddings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        # Ollama exposes an OpenAI-compatible API at <base>/v1; api_key is ignored.
        self._embed_client = OpenAI(
            base_url=self.settings.ollama_base_url.rstrip("/") + "/v1",
            api_key="ollama",
        )

    # --- embeddings -------------------------------------------------------
    def embed(self, text: str) -> list[float]:
        resp = self._embed_client.embeddings.create(
            model=self.settings.embed_model, input=text
        )
        vec = resp.data[0].embedding
        if len(vec) != self.settings.embed_dim:
            raise RuntimeError(
                f"Embedding dim {len(vec)} != expected {self.settings.embed_dim}. "
                f"Model/schema mismatch — check EMBED_MODEL and VECTOR(<DIM>)."
            )
        return vec

    # --- connection -------------------------------------------------------
    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.settings.database_url)

    def ping(self) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return cur.fetchone()[0] == 1

    # --- per-agent semantic memory ---------------------------------------
    def store_memory(self, agent: str, content: str, metadata: dict[str, Any] | None = None) -> int:
        """Store a memory, de-duplicated by exact content.

        If identical content already exists, returns the existing id without
        re-embedding (saves an Ollama call) or inserting a duplicate row.
        """
        schema = _schema_for(agent)
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._connect() as conn, conn.cursor() as cur:
            # de-dup check first — skip embedding entirely if it already exists
            cur.execute(
                f"SELECT id FROM {schema}.memories WHERE content_sha256 = %s;", (sha,)
            )
            existing = cur.fetchone()
            if existing:
                return existing[0]

            emb = self._vec_literal(self.embed(content)) if content else None
            cur.execute(
                f"INSERT INTO {schema}.memories (content, content_sha256, metadata, embedding) "
                f"VALUES (%s, %s, %s::jsonb, %s::vector) "
                f"ON CONFLICT (content_sha256) DO NOTHING RETURNING id;",
                (content, sha, json.dumps(metadata or {}), emb),
            )
            row = cur.fetchone()
            if row:
                return row[0]
            # lost a race: another writer inserted the same content — fetch it
            cur.execute(
                f"SELECT id FROM {schema}.memories WHERE content_sha256 = %s;", (sha,)
            )
            return cur.fetchone()[0]

    def search_memory(self, agent: str, query: str, k: int = 5) -> list[dict[str, Any]]:
        schema = _schema_for(agent)
        qvec = self._vec_literal(self.embed(query))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id, content, metadata, embedding <=> %s::vector AS distance "
                f"FROM {schema}.memories ORDER BY distance ASC LIMIT %s;",
                (qvec, k),
            )
            rows = cur.fetchall()
        return [
            {"id": r[0], "content": r[1], "metadata": r[2], "distance": float(r[3])}
            for r in rows
        ]

    def count_memories(self, agent: str) -> int:
        schema = _schema_for(agent)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {schema}.memories;")
            return cur.fetchone()[0]

    # --- shared orchestration state (memory_common.agent_state) -----------
    def save_state(self, state_id: str, agent: str, kind: str, data: dict[str, Any]) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory_common.agent_state (id, agent, kind, data) "
                "VALUES (%s, %s, %s, %s::jsonb) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, "
                "agent = EXCLUDED.agent, kind = EXCLUDED.kind, updated_at = now();",
                (state_id, agent, kind, json.dumps(data)),
            )

    def latest_state(self, kind: str, agent: str | None = None) -> dict[str, Any] | None:
        clause = "WHERE kind = %s" + (" AND agent = %s" if agent else "")
        params: tuple[Any, ...] = (kind, agent) if agent else (kind,)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id, agent, kind, data, updated_at FROM memory_common.agent_state "
                f"{clause} ORDER BY updated_at DESC LIMIT 1;",
                params,
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "agent": row[1], "kind": row[2], "data": row[3], "updated_at": row[4].isoformat()}

    # internal: expose the literal helper as a method too
    def _vec_literal(self, embedding: list[float]) -> str:  # noqa: D401
        return _vec_literal(embedding)
