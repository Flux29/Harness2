# ADR-0009 — Observability: Logfire (cloud) + remote MCP for diagnostics

**Status:** Accepted · 2026-06-30

## Context
Diagnosing the bootstrap loop by pasting stack traces is slow and lossy. We want
real-time visibility into agent runs, tool calls, token usage, HTTP calls, and
graph node spans — and ideally a way for the assisting model(s) to query that
telemetry directly during diagnosis.

## Decision
- **Instrumentation:** Pydantic **Logfire** (cloud), the native OTel platform for
  pydantic-ai/pydantic-deep. Wired via an env-gated `observability.setup_observability()`
  (`logfire.configure()` + `instrument_pydantic_ai()` + `instrument_httpx()`),
  no-op unless `LOGFIRE_TOKEN` is set, called at the top of the check entrypoints.
  OTel under the hood, so a self-hosted collector (Jaeger/Grafana) is a future
  swap via `OTEL_EXPORTER_OTLP_ENDPOINT` with no code change.
- **Model-queryable telemetry:** Logfire's **remote MCP server**
  (`https://logfire-us.pydantic.dev/mcp`), exposing `find_exceptions`,
  `find_exceptions_in_file`, `arbitrary_query` (SQL over OTel traces/metrics),
  `get_logfire_records_schema`. Auth via a **read token** (`project:read` scope)
  as an `Authorization: Bearer` header (deterministic) or OAuth browser flow.
  Registered at **user scope** in `~/.claude.json`.

## Consequences
- Per-run traces, token/cost, and node timelines are visible live; click a trace
  for the span waterfall.
- The read token is separate from the write token (`LOGFIRE_TOKEN` in `.env`);
  keep both out of git.
- Open caveat: the remote MCP was configured via the `claude` CLI; whether its
  tools surface inside **Cowork** (vs. Claude Code) is scope-dependent and to be
  verified after restart. If not surfaced, register through Cowork's connector
  settings instead. The standalone `uvx logfire-mcp` stdio server still exists but
  the remote server is the current, faster-iterating path.
