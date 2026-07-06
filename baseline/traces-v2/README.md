# baseline/traces-v2 — gate-6 Logfire trace summaries (the v2 telemetry baseline)

Captured 2026-07-06 in the exit-gate-6 live session via the Logfire MCP
(project `flux/deep-agents`). `gate6-trace-summaries.json` records, per
scenario: trace id, span counts, gated-tool span counts, and the Matrix E
row verdicts (model attribute, cost resolution, token fields, MCP
`tools/list` handshakes, interrupt span property, exception scan).

All Matrix E rows verified against the traces-v1 README's rule set (the v1
placeholders were never populated; this is the first committed telemetry
ground truth, and the baseline future live sessions diff against).
