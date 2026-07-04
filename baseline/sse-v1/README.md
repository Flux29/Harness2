# baseline/sse-v1 — live SSE transcripts (Parity Matrix C, wire protocol)

These are the ground truth for the AG-UI wire-protocol parity matrix: raw SSE
transcripts of the `LIVE WIRE OK` flow and one `TestModel` run per thread
scenario. They are **live captures** and are produced in the local gate sessions
(gates 2, 5, 6), NOT in offline CI — CI has no network and no token.

All live inference is pinned to `openrouter:z-ai/glm-5.2` (see plan 3.4). Mixing
models between baseline and verification runs makes Matrix C/E diffs
unattributable to code changes.

## What to capture (one file per scenario, raw `data:`-framed SSE)
- `chat-roundtrip.sse` — a plain chat turn (`RUN_STARTED` … `RUN_FINISHED`)
- `todo-render.sse` — a turn that renders todos
- `interrupt-deny.sse` and `interrupt-approve.sse` — an approval interrupt, both
  paths (`outcome.interrupts[].id/reason`, resume acceptance shape)

## The offline slice already covered by CI
The 422 body shape and the endpoint shapes (`/healthz`, `/debug/mcp`) are
captured offline in `baseline/endpoints-v1/` and enforced by the `parity` job.
Only the streaming event sequences require these live transcripts.

> Status at Phase 0: placeholder. Populate during the first live gate session.
