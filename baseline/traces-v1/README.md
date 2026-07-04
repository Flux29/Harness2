# baseline/traces-v1 — live Logfire trace summaries (Parity Matrix E)

Ground truth for the telemetry parity matrix. For every live baseline run,
export a span summary (NOT the raw trace) to `<scenario>.json` with:

- root span name + `service_name`
- span-tree shape (parent→child span names), timing-independent
- model-call span count, and the `model` attribute on each (must read
  `z-ai/glm-5.2` in every model span — a stray 4.6/5.1 span fails parity)
- tool-execution span count + tool names; MCP `tools/list` handshakes per
  enabled server under the deployed roster
- token-usage fields present (input/output) — presence only, values vary
- cost fields resolve (> 0 for OpenRouter spans)
- interrupt scenario: run-1 trace ends without the gated tool span; run-2
  contains exactly one
- error/exception spans: zero unexpected

Pull each run's trace via the Logfire MCP and record the trace id. The parity
harness gains a `--live` mode (run locally at gates 2, 5, 6) that diffs the
current run's summary against these files. Timing, span durations, and token
*values* are out of scope; structure, counts, names, and attribute presence are
in scope.

> Status at Phase 0: placeholder. Populate during the first live gate session.
> A local `LOGFIRE_TOKEN` is already wired (the capture run logs a project URL),
> so this is capturable as soon as a live `glm-5.2` run is executed.
