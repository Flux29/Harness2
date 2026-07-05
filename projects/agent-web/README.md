# agent-web — AG-UI web service (ADR-0012…0016)

One deep agent (vendored `pydantic-deepagents`, full feature set), one FastAPI
route (`POST /agent`, AG-UI SSE), one CopilotKit React frontend. Simplicity is
genius: the protocol, encoder, and security defaults come from `pydantic-ai`;
we own ~150 lines of Python and one React component.

## Quick start (single-server mode — PLAN Phase 1)

```powershell
cd <workspace-root>\projects\agent-web
powershell -File scripts\build-frontend.ps1     # once, and after UI changes
powershell -File scripts\Start-AgentWeb.ps1     # starts server if needed, opens browser
```

One process, one port: `http://localhost:8801` serves UI + agent (no CORS, no
Node at runtime). Secrets come from Windows USER env vars (`setx`), not .env.
Optional: `scripts\Create-DesktopShortcut.ps1 -IconPath you.ico` (one-click
icon) and `scripts\Register-StartupTask.ps1` (auto-start at logon +
self-restart). Dev mode with hot reload still works: `npm run dev` in
frontend\ (:3000, proxies /agent to :8801).

## Backend (Windows PowerShell)

```powershell
cd <workspace-root>\projects\agent-web
uv venv                                   # local .venv (never inside vendor\)
uv sync                                   # installs harness FROM vendor\ (see pyproject [tool.uv.sources])
uv run uvicorn agent_web.main:app --host 127.0.0.1 --port 8801
```

Env (all optional; `.env` supported): `AGENT_MODEL` (default
`openrouter:z-ai/glm-5.2` — needs `OPENROUTER_API_KEY`), `FALLBACK_MODEL`
(auto-retry model), `WORKSPACES_DIR`, `MCP_CONFIG`, `MCP_ENABLE` (default
`context7,deepwiki`), `CORS_ORIGINS`, `COST_BUDGET_USD`, `SKILLS_DIR`,
`WEB_TOOLS=0` (required for TestModel), `TRACING=0`.

Feature switches (ADR-0015), all OFF by default — flip in `.env`, restart:

| flag | enables | prerequisites |
|---|---|---|
| `TEAMS=1` | agent teams: shared todos + message bus | none |
| `TOOL_SEARCH=1` | search-on-demand tool schemas (token saver) | none; flip when MCP roster grows |
| `EXECUTE=1` | shell execute tool, **approval-gated** (AG-UI interrupt) | `uv sync --extra full` for Docker sandbox backend |
| `BROWSER_AUTOMATION=1` | Playwright browser automation | `--extra full` + `playwright install chromium` |
| `FORKING=1` | Live Run Forking — branches **run LLM-generated code + its pytest suite on the host** (no approval interrupt exists for `test_command`); enable only if you accept that | none |
| `LITEPARSE=1` | PDF/DOCX/XLSX parsing | `--extra full` + Node ≥ 18 |

Offline (no keys): `uv run python scripts\dev_server_testmodel.py`

Routes: `POST /agent` (AG-UI), `GET /healthz`, `GET /debug/mcp` (answers "why is
this tool missing").

## Frontend

```powershell
cd frontend
npm install        # package-lock.json is committed (built & verified 2026-07-02)
npm run dev        # http://localhost:3000 -> backend on :8801
```

OSS-only (ADR-0016): no CopilotKit account, no `INTELLIGENCE_*` env vars.
Optional, later: `npx copilotkit@latest skills onboard` installs CopilotKit
coding-agent skills + agent-assisted onboarding (account-free per CLI docs).

## Tests (all E2E, no mocks of our code)

```powershell
uv run pytest      # 10 tests: SSE shape, 422, history persistence, thread
                   # isolation, healthz/mcp, approval interrupt (tool NOT run)
uv run python ..\..\vendor\verify_core.py   # harness+patch+AG-UI+MCP gate
```

## Design decisions live in `docs/adr/` (0012–0016)
- Per-thread isolation = per-request `WebDeps` with `LocalBackend` under
  `workspaces/<thread>/` (`deps.py`, unit-tested).
- Server-owned history (`history.py`) keyed by AG-UI `threadId` — client
  history is untrusted (adapter trust model).
- Approvals: `requires_approval=True` tools pause into AG-UI interrupts
  (`output_type=[str, DeferredToolRequests]` — supported natively by
  `create_deep_agent`, ADR-0012 risk 1 resolved).
- MCP: harness-native registry; builtins + `mcp.json` (`mcpServers` format);
  only enabled+authenticated servers load; degraded servers never break a run.

## MCP roster (ADR-0014) — how to enable more

`mcp.json` ships two stdio servers, OFF by default. Enable by adding the name
to `MCP_ENABLE` (comma-separated) and providing the env var:

| name | needs | gives the agent |
|---|---|---|
| `github` (builtin) | `GITHUB_MCP_PAT` | repos, issues, PRs, code search |
| `logfire` | `LOGFIRE_READ_TOKEN` (read token, not the write token) + `uv` | **self-diagnosis: the agent queries its own traces** |
| `postgres` | `DATABASE_URL` + the pgvector Docker stack up + Node | SQL over the eval-optimizer memory DB |

Example `.env` line: `MCP_ENABLE=context7,deepwiki,github,logfire`
Check `GET /debug/mcp` — enabled+authenticated shows `"status":"ready"` (it loads on the next run).
stdio servers spawn subprocesses on this host; keep the roster deliberate.
