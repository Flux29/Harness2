# Exit gate 6 — live end-to-end session evidence (2026-07-06)

Environment: Windows, refactored working copy (`refactor/phases-4-6`) served on
`127.0.0.1:8802` (deployed 8801 instance untouched); all inference
`openrouter:z-ai/glm-5.2`; deployed MCP roster `context7,deepwiki,github,logfire`
(all `ready`, all `in_agent`); `FORKING=1`, `EXECUTE=1`,
`BROWSER_AUTOMATION=0`, `LITEPARSE=0` (dev venv, no `full` extra).
Total live spend: ≈ $2.5 OpenRouter (incl. 5 exploratory fork runs while
isolating the fork-runner defect).

## Checklist (plan §exit gate 6) → evidence

| Requirement | Result | Evidence |
|---|---|---|
| Chat round-trip | PASS | `sse-v2/chat-roundtrip.sse` — deltas spell `LIVE WIRE OK` |
| Todo rendering | PASS | `sse-v2/todo-render.sse` — full `write_todos` TOOL_CALL sequence |
| Interrupt: deny path | PASS | `sse-v2/interrupt-deny.sse` — pause, `resume approved=false`, "tool call was denied", zero executions |
| Interrupt: approve path | PASS | `sse-v2/interrupt-approve.sse` — executed exactly once after approval |
| MCP discovery via `search_tools` | PASS | `sse-v2/mcp-discovery.sse` — 10 `github_*` + 4 `logfire_*` prefixed tools |
| Gated fork run (6.1 metric) | PASS | negative: refusal without `EVALOPT_ALLOW_HOST_EXEC=1`; positive: 2/3 branches `tests=1.00`, winner by stated tie-break, merged, exit 0 — the first successful live ADR-0018 run |
| Restart + history resume | PASS | `sse-v2/restart-resume.sse` — post-restart recall from server-side history |
| Matrix C (wire shapes) | PASS | all required event types present; `REASONING_*` additive; 422 row extended by `disc-422-serialization-crash` |
| Matrix D (endpoints) | PASS | `endpoints-v2/` — healthz/debug-mcp additive-only vs v1 (`frontend_mounted`, `in_agent`); deployment-config row: enabled set exactly `{context7,deepwiki,github,logfire}` |
| Matrix E (telemetry) | PASS | `traces-v2/gate6-trace-summaries.json` — model attr 5.2 on all 308 chat spans, cost > 0, tokens present, `tools/list` handshakes, interrupt span property exact, zero unexpected exceptions |

## Live finds (the session doing its job)

1. **`disc-422-serialization-crash`** — non-UTF-8 request body crashed the 3.2
   422 handler into a raw 500. Pinned red-first, fixed
   (`errors(include_input=False)` fallback), manifest + test same-commit.
2. **`disc-fork-test-command-import-path`** — the default fork
   `test_command` could never pass an honest branch (console-script `pytest`
   lacks cwd on `sys.path`; then bare `python` resolved to uv's pytest-less
   managed base in the vendor's no-shell spawn context). Diagnosed with an
   instrumented `FORK_TEST_COMMAND` proving snapshots were correct; fixed by
   pinning the absolute running interpreter + `-m pytest -q`. ADR-0018's
   metric had never run live before this session (gate 5 ran forking-off).
3. **ISSUE-7 (vendor, open)** — `BranchOverlay.grep_raw()` signature mismatch
   (plus abs-path `glob` `NotImplementedError`) crash branch agents' tool
   calls inside overlays; fail-contained by the coordinator. Vendor is
   read-only: future patch-file/upstream decision.
4. **Hygiene**: live `NVIDIA_API_KEY` found in gitignored `.env` (standing
   rule 4 violation; never committed — secrets-scan stays green). Removed;
   **rotate the key**.

These transcripts and trace summaries are the v2 baseline going forward.
