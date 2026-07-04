# RUNBOOK — live smoke test (agent-web)

The **living** copy of the "LIVE WIRE OK" smoke procedure, extracted from the now-
frozen `HANDOFF.md`. All live inference is `openrouter:z-ai/glm-5.2`.

## Prerequisites
- `OPENROUTER_API_KEY` set as a **USER environment variable** (`setx`), not in `.env`.
- Dependencies synced: `cd projects/agent-web && uv sync`.

## 1. Start the server (port 8801)
```powershell
cd projects\agent-web
uv run uvicorn agent_web.main:app --host 127.0.0.1 --port 8801
```

## 2. Fire the smoke request (second terminal)
```powershell
curl.exe -N -X POST http://127.0.0.1:8801/agent -H "content-type: application/json" ^
  -d "{\"threadId\":\"live-1\",\"runId\":\"r1\",\"messages\":[{\"id\":\"m1\",\"role\":\"user\",\"content\":\"Reply with exactly: LIVE WIRE OK\"}],\"tools\":[],\"context\":[],\"state\":{},\"forwardedProps\":{}}"
```
Expect `TEXT_MESSAGE_CONTENT` deltas spelling `LIVE WIRE OK`, then `RUN_FINISHED`.

## 3. Health & MCP
```powershell
curl.exe http://127.0.0.1:8801/healthz
curl.exe http://127.0.0.1:8801/debug/mcp
```

Notes:
- `--host 127.0.0.1` is the stated bind invariant (pinned in the startup scripts
  by step 5.3); uvicorn already defaults to loopback.
- **8801** is the single-server port. (`HANDOFF.md` shows an older port from the
  original host, held then by Docker; that is frozen history — always use 8801.)
