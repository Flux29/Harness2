# ADR-0001 — Windows-native workspace; DevDrive/Hyper-V VM deferred

**Status:** Accepted · 2026-06-29

## Context
Three prior plans pulled in different directions: a Windows workspace
(`AgenticWork`), a Linux DevDrive Hyper-V VM with `/etc/claude-code` managed
settings, and a 5-agent RAG port. Codex had already built ~70% of the Windows
workspace. Maintaining both a Windows root and a Linux VM root would double the
setup surface and split the work.

## Decision
Use a **Windows-native** `<workspace-root>` (an `AgenticWork` root under the
user's profile) as the single working root.
Defer the DevDrive/Hyper-V Linux VM and managed-settings governance layer
indefinitely. Stateful services run in Docker Desktop containers; agent code runs
on the Windows host under `uv`.

## Consequences
- One environment to reason about; reuses Codex's existing scaffold.
- Lose the VM's hard isolation/governance — acceptable for a single-engineer
  research build; revisit if this ever needs multi-user or regulated controls.
- Docker Desktop (WSL2 GPU) becomes the dependency for Postgres/Ollama/GPU, which
  proved workable (GPU passthrough confirmed via in-container `nvidia-smi`).
