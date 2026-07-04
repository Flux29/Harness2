# ADR-0003 — Provider-flexible, per-role inference + rate-limit resilience

**Status:** Accepted · 2026-06-29 (supersedes the NVIDIA-only inference choice in PDR v1.0)

## Context
The plan started on NVIDIA's free GLM 5.1 endpoint. GLM 5.1 produced an excellent
plan, but the free tier then hit a **hard quota/credit wall**: a single,
sequential call returned 429 across ~4.5 minutes of exponential backoff — not a
per-minute throttle. We also tested a local model (`qwen2.5-coder:7b` on an 8 GB
RTX 3000 Ada): it could not reliably produce structured output — it emitted
tool-call envelopes as text and, under the full harness, wandered into calling
harness tools (e.g. `start_monitor`). Different roles have very different
quality/volume needs (one Planner call vs. many Generator/Critic calls).

## Decision
Make inference **provider-flexible and configurable per role** via
`PLANNER_MODEL` / `GENERATOR_MODEL` / `CRITIC_MODEL`. `build_model()` resolves:
- `ollama:<name>` → local Ollama (OpenAI-compatible) — free, offline.
- `openrouter:<name>` → OpenRouter (OpenAI-compatible) — **primary path**,
  `openrouter:z-ai/glm-5.1` (~$0.98/$3.08 per 1M).
- `anthropic:…` / other `provider:model` → resolved natively by pydantic-ai —
  used for high-reasoning roles (Claude Sonnet/Opus) when bootstrapping.
- bare id (`z-ai/glm-5.1`) → NVIDIA endpoint.

Add **rate-limit resilience** (`runtime.py`): exponential backoff on 429 and a
concurrency cap (`gather_limited`, default sequential).

## Consequences
- No single-provider lock-in; switch a role with one env var.
- A capable model (Sonnet/Opus or GLM-via-OpenRouter) handles structured roles;
  local models are reserved for non-structured/cheap work and embeddings.
- API access is **billed separately** from Claude Pro/Max subscriptions.
- Confirm the exact OpenRouter slug; secrets stay in gitignored `.env`.
