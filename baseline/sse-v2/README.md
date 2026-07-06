# baseline/sse-v2 — gate-6 live SSE transcripts (the v2 wire baseline)

Captured 2026-07-06 in the exit-gate-6 live session, against the refactored
working copy on `127.0.0.1:8802` (deployed MCP roster; all inference
`openrouter:z-ai/glm-5.2`). Per the plan, this session's transcripts become
the **v2 baseline** the parity harness carries forward.

| File | Scenario | Key wire facts |
|---|---|---|
| `chat-roundtrip.sse` | plain chat turn | `RUN_STARTED` … `TEXT_MESSAGE_*` deltas spelling `LIVE WIRE OK` … `RUN_FINISHED` |
| `todo-render.sse` | todo tool turn | `TOOL_CALL_START(write_todos)` → `ARGS` → `END` → `RESULT` ("Updated 2 todos") |
| `interrupt-deny.sse` | approval interrupt, deny | run 1 pauses (`outcome.interrupts[].id/reason`); run 2 (`resume[]`, approved=false) → `TOOL_CALL_RESULT: The tool call was denied.`; tool never executed |
| `interrupt-approve.sse` | approval interrupt, approve | run 2 (approved=true) → tool executed exactly once, probe echoed |
| `mcp-discovery.sse` | search_tools discovery | two `search_tools` calls; 10 `github_*` + 4 `logfire_*` prefixed tools reported |
| `restart-resume.sse` | restart + history resume | post-restart run on the same thread recalls pre-restart content |

New vs the Matrix C v1 row set: `REASONING_*` event types (GLM-5.2 reasoning
deltas surfaced by the AG-UI adapter) — **additive**; all v1-required event
types present. The one intentional wire diff vs v1 remains the 3.2 422 body
(plus the gate-6 hardening for non-UTF-8 bodies, `disc-422-serialization-crash`).

sse-v1 was never populated (placeholder since Phase 0); these files are the
first committed wire ground truth.
