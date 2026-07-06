# agent-web — operating notes (shared across all threads)

This file lives in `projects/agent-web/context/` and is seeded into every
thread workspace by the deps factory, so the harness injects it into every
session. The improve pipeline (`python -m agent_web.improve_run --apply`)
appends its accepted proposals here — keep entries short and imperative.

## Tool selection

- Web lookups use `web_search` / `web_fetch` — never `execute` with
  curl/urllib/Invoke-WebRequest. `execute` is for LOCAL commands only and
  costs the user an approval click. (Learned 2026-07-06: a session fetched
  python.org via `python -c urllib` and burned an interrupt on it.)
- For external services (GitHub, library docs, telemetry), call
  `search_tools` first, then use the discovered `github_*` / `context7_*` /
  `logfire_*` tools — never shell equivalents.
