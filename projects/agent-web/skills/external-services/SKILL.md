---
name: external-services
description: "Correct tool discovery and usage for GitHub, docs, telemetry, and other external services"
tags: [mcp, github, tool-search, discipline]
version: "1.0.0"
---

# External Services: Discover, Don't Improvise

Lesson learned 2026-07-03 (trace-verified): with tool search enabled, MCP
tools are NOT in your visible toolbox. Improvising with shell/browser
instead of searching caused failed runs (winget install attempts, browser
login pages, invalid selectors like `[Sign in]`).

## The recipe

1. Task mentions GitHub / library docs / telemetry / a database?
   -> `search_tools` FIRST with 2-3 keywords (e.g. "github create repository").
2. Use what search returns:
   - GitHub: `github_create_repository`, `github_create_or_update_file`,
     `github_search_code`, etc. (already authenticated via PAT — no login).
   - Library docs: `context7_*`; repo Q&A: `deepwiki_*`; own traces: `logfire_*`.
3. Shell (`execute`) is for local work: running code, git in the workspace.
   It is approval-gated — every call interrupts the user. Spend those
   interruptions on things only the shell can do.
4. Browser automation is a LAST resort for tasks with no tool coverage,
   and NEVER for logging in anywhere.

## Known-good GitHub sequence (verified against Flux29/Harness, refined 2026-07-03)

    search_tools {"queries": ["github", "create repository"]}
    github_create_repository {"name": "...", "autoInit": false, "description": "..."}
    github_create_or_update_file {"owner": "...", "repo": "...", "path": "README.md", ...}

Pitfalls (each one observed in a real trace):
- `organization` param: personal accounts are NOT organizations — omit it
  for repos under the user's own account.
- `autoInit: true` creates a DEFAULT README at birth; updating an existing
  file then REQUIRES its `sha` or the API rejects with 422. When the user
  wants specific README content, use `autoInit: false` and create the file
  yourself — or fetch the file first and pass its sha.
- ALWAYS verify a write landed: re-read the file (github_get_file_contents)
  and compare before telling the user it succeeded. A tool error buried in
  a result is still a failure; never report success you did not confirm.
