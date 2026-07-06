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
- The `POST /agent` guard (ADR-0020) requires `content-type: application/json`
  and a loopback `Host` — the curl above satisfies both. If `AGENT_TOKEN` is
  set, add `-H "Authorization: Bearer <token>"`.
- **8801** is the single-server port. (`HANDOFF.md` shows an older port from the
  original host, held then by Docker; that is frozen history — always use 8801.)

## 4. Thread persistence smoke (feat-thread-persistence / feat-run-survival)

Manual checklist for the session-persistence surfaces (ADR-0023); run in the
browser against the built frontend, and once against `npm run dev` (proxy):

1. Chat a couple of turns, reload the page → the transcript (including tool
   cards) reappears and the sidebar highlights the same thread.
2. Switch between two threads in the sidebar → transcripts swap with no
   bleed-through.
3. "+ New thread" → blank chat; the thread appears in the sidebar with the
   first prompt as its title after the first run.
4. With `EXECUTE=1`: trigger an approval interrupt, reload → the Approve/Deny
   banner REAPPEARS (no `pending interrupt(s) not addressed` error). Approve →
   the tool executes exactly once; on a fresh interrupt, Deny → the run
   resumes with the denial. The sidebar shows/clears the ⚠️ badge.
5. Reload the page while a run is mid-flight → the sidebar shows ⏳ for that
   thread; when it clears, reopening the thread shows the COMPLETED result
   (the run survived the disconnect and saved server-side).
6. `?thread=<id>` attaches to a specific thread; `?new=1` starts fresh.
7. `curl http://127.0.0.1:8801/threads` lists threads with titles and flags.
