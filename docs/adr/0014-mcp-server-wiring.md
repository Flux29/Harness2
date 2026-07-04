# ADR-0014 — MCP server wiring via the harness-native registry

**Status:** Accepted · 2026-07-01 · Extends ADR-0009 (Logfire diagnostics via MCP);
feeds the agent built in ADR-0012.

## Context
The goal is to wire as many useful MCP servers as possible into the deep agent. The
vendored harness already ships a complete, PydanticAI-native MCP subsystem
(`pydantic_deep/mcp/`, extra `.[mcp]` → `pydantic-ai-slim[mcp]` +
`py-key-value-aio[disk]` for OAuth token persistence):

- `MCPServerConfig` — transports `stdio | http | sse`; auth kinds
  `none | bearer | header | env | oauth`.
- `parse_mcp_servers()` — ingests the de-facto standard `mcpServers` JSON mapping
  (same shape as Claude Desktop / Cursor configs), with `${VAR}` env expansion;
  malformed/WebSocket entries are skipped with a warning, not fatal.
- `MCPRegistry` — add/remove/enable/status; `auth_satisfied()` checks secrets before
  connect; `build_active(on_degraded=…)` returns toolsets for every server that is
  enabled *and* authenticated, each pre-wrapped in `make_resilient()` so one dead
  server degrades ("tools absent, `on_degraded` fired") instead of breaking the run;
  `probe_mcp_server()` for health checks.
- Builtins (`builtins.py`, all default-disabled): `github` (hosted, bearer
  `GITHUB_MCP_PAT`), `figma` (hosted, OAuth), `figma-local`, `context7`, `deepwiki`.

`create_deep_agent(mcp_servers=...)` accepts the built toolsets directly. Writing any
custom MCP client/loader would duplicate all of this.

## Decision
**All MCP wiring goes through `pydantic_deep.mcp`. Config is one `mcp.json` file in
the `mcpServers` format; secrets are env vars; only enabled+authenticated servers
load.**

Startup recipe in `projects/agent-web/`:

```python
registry = MCPRegistry(builtin_mcp_servers() + parse_mcp_servers(json.load(open("mcp.json"))["mcpServers"]))
toolsets = registry.build_active(on_degraded=log_degraded)  # already make_resilient-wrapped
agent = create_deep_agent(mcp_servers=toolsets, ...)
```

Initial roster ("as many as possible", curated by non-overlap):

| Server | Transport | Auth | Why |
|---|---|---|---|
| `github` (builtin) | http | bearer `GITHUB_MCP_PAT` | repos, issues, PRs, code search |
| `context7` (builtin) | http | none/key | current library docs for codegen |
| `deepwiki` (builtin) | http | none | repo-level docs Q&A |
| `figma` (builtin) | http | oauth | design context (enable when needed) |
| `logfire` | http (remote) | token | self-diagnostics per ADR-0009 — the agent can query its own traces |
| `postgres` (stdio) | stdio | env DSN | direct SQL over the ADR-0004 pgvector store (`infra/docker-compose.yml`, port 5433) |

**Deliberately excluded:** filesystem, fetch/web-search, and shell MCP servers — the
harness has native equivalents (`include_filesystem`, `web_search`/`web_fetch`,
execute backends). Duplicate tools burn context tokens and confuse tool selection.
Simplicity is genius: one capability, one tool.

## Status (2026-07-03 — live, with two trace-verified lessons)
Roster in production: github, context7, deepwiki (builtins) + logfire (stdio,
official logfire-mcp). All toolsets are PrefixedToolset-wrapped (`github_*` …)
after a real name collision (github's `delete_file` vs the forking toolset's —
pydantic-ai aborts runs on duplicates). Interplay with `tool_search=True`
(ADR-0015): MCP tools become INVISIBLE to the model until it calls
`search_tools` — without explicit instruction + the `external-services` skill,
models improvise with shell/browser instead. Instructions and skill now teach
search-first; verified unsteered on 2026-07-03 (trace: search_tools →
github_create_repository). Resilient degradation observed repeatedly in
production (context7/logfire connection failures never broke a run).

## Consequences
- Adding a server is a JSON entry + an env var — no code. The same `mcp.json` is
  readable by other MCP-aware tools.
- `build_active()` + `make_resilient()` means a missing PAT or a down server softens
  to "these tools are absent this run" — the agent always boots.
- stdio servers spawn subprocesses on the web host; they inherit the service's
  filesystem view. Keep stdio entries minimal (postgres only, initially) and prefer
  hosted/http where offered. OAuth tokens persist on disk via `py-key-value-aio[disk]`
  — that cache location must be excluded from backups/commits.
- Tool-count growth is real (GitHub's server alone is large). If the toolset bloats,
  `create_deep_agent(tool_search=True)` (harness feature, ADR-0015) exposes tools via
  search instead of flat listing — flip that switch before inventing filtering.
- Registry `status()` output should surface in an admin/debug route so "why is this
  tool missing" is answerable in one request.

## Validation (when implemented)
With `GITHUB_MCP_PAT` set: `registry.status()` reports github active; a prompt
exercising a GitHub search succeeds; killing the postgres container mid-session
degrades gracefully (resilient wrapper) without aborting the run; unset PAT →
server skipped at build, boot still clean.
