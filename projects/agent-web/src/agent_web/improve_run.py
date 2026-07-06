"""Headless improve runner (feat-improve-loop) — deterministic self-improvement.

The vendor's improve pipeline is agent-callable only and points at a sessions
directory agent-web never writes, so left alone it (a) never runs and (b)
would analyze zero sessions. This runner closes both gaps deterministically:

1. stages ``state/history/*.json`` (agent-web's real transcripts) into the
   analyzer's expected ``<session>/messages.json`` layout — same JSON format,
   mtimes preserved so the analyzer's recency window works;
2. runs :class:`ImprovementAnalyzer` on the decided workspace model
   (``settings.model`` — never the vendor's non-GLM default) with the shared
   ``context/`` directory as the proposal target, so accepted changes reach
   every future thread via the deps-factory seeding;
3. prints the report. **Report-only by default** — pass ``--apply`` to write
   proposals at or above ``--min-confidence``. An LLM editing the context
   files that steer future LLM sessions should be watched before it is
   trusted.

Run:  uv run python -m agent_web.improve_run [--days 7] [--max-sessions 20]
          [--focus AREA] [--apply] [--min-confidence 0.7]

Scheduled nightly by scripts/Register-ImproveTask.ps1 (report-only).
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

# The documented feature package, not a deprecated shim — the Gate 5 layer
# contract bans only pydantic_deep.toolsets.forking; the improve feature has
# no public top-level export to use instead.
from pydantic_deep.features.improve.analyzer import ImprovementAnalyzer
from pydantic_deep.features.improve.types import ImprovementReport

from . import observability
from .settings import Settings

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # projects/agent-web

# Logical context-file names -> paths relative to the project root (the
# analyzer's working_dir). Proposals land in the SHARED context/ dir, never a
# per-thread workspace, so the deps factory propagates them.
CONTEXT_FILES = {
    "SOUL.md": "context/SOUL.md",
    "AGENTS.md": "context/AGENTS.md",
    "MEMORY.md": "context/MEMORY.md",
}


def _resolve(p: Path) -> Path:
    return p if p.is_absolute() else _PROJECT_ROOT / p


def stage_sessions(history_dir: Path, staging_dir: Path) -> int:
    """Stage ``<history>/<slug>.json`` as ``<staging>/<slug>/messages.json``.

    The staging dir is rebuilt from scratch each run (it is derived state).
    ``copy2`` preserves mtimes — the analyzer's day-window discovery filters
    on the mtime of each staged ``messages.json``."""
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    if not history_dir.is_dir():
        return 0
    staged = 0
    for hist in sorted(history_dir.glob("*.json")):
        dest = staging_dir / hist.stem / "messages.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hist, dest)
        staged += 1
    return staged


def format_report(report: ImprovementReport) -> str:
    lines = [f"Analyzed {report.analyzed_sessions} sessions ({report.time_range})"]
    if report.failed_sessions:
        lines.append(f"  ({report.failed_sessions} sessions failed extraction)")
    if not report.proposed_changes:
        lines.append("No changes proposed.")
        return "\n".join(lines)
    lines.append(f"Proposed {len(report.proposed_changes)} change(s):")
    for i, change in enumerate(report.proposed_changes, 1):
        lines.append("")
        lines.append(f"{i}. {change.target_file} ({change.change_type}) "
                     f"confidence={change.confidence:.2f}")
        lines.append(f"   Reason: {change.reason}")
        preview = change.content[:300] + ("..." if len(change.content) > 300 else "")
        lines.append(f"   Content: {preview}")
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> int:
    observability.configure()  # traces to Logfire when LOGFIRE_TOKEN is set
    settings = Settings()

    # --state-dir overrides settings (Settings reads STATE_DIR at import time,
    # so a late env change can't; the explicit arg also serves tests and ops).
    state_dir = Path(args.state_dir) if args.state_dir else Path(settings.state_dir)
    history_dir = _resolve(state_dir) / "history"
    staging_dir = _resolve(state_dir) / "improve" / "sessions"

    staged = stage_sessions(history_dir, staging_dir)
    print(f"Staged {staged} session(s) from {history_dir}")
    if staged == 0:
        print("Nothing to analyze.")
        return 0

    analyzer = ImprovementAnalyzer(
        model=settings.model,  # the decided workspace model, never the vendor default
        sessions_dir=staging_dir,
        working_dir=_PROJECT_ROOT,
        context_files=CONTEXT_FILES,
        on_progress=lambda stage, cur, tot: print(
            f"  [{stage}]" + (f" {cur}/{tot}" if tot else ""), flush=True),
    )
    report = await analyzer.analyze(
        days=args.days, max_sessions=args.max_sessions, focus=args.focus)
    print()
    print(format_report(report))
    if report.analyzed_sessions:
        analyzer.save_improve_state(report)

    if not args.apply:
        if report.proposed_changes:
            print(f"\nReport-only. Re-run with --apply to write changes with "
                  f"confidence >= {args.min_confidence}.")
        return 0

    accepted = [c for c in report.proposed_changes if c.confidence >= args.min_confidence]
    if not accepted:
        print("\n--apply: no proposals met the confidence threshold; nothing written.")
        return 0
    modified = await analyzer.apply_changes(accepted)
    print(f"\nApplied {len(accepted)} change(s): {', '.join(modified)}")
    print("Seeded into each thread workspace on its next request (deps factory).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent_web.improve_run",
        description="Analyze recent sessions and propose context-file improvements.")
    parser.add_argument("--days", type=int, default=7,
                        help="look-back window for sessions (default 7)")
    parser.add_argument("--max-sessions", type=int, default=20,
                        help="cap on sessions analyzed, most recent first (default 20)")
    parser.add_argument("--focus", default=None,
                        help="optional focus area, e.g. 'tool selection'")
    parser.add_argument("--apply", action="store_true",
                        help="write accepted proposals (default: report only)")
    parser.add_argument("--min-confidence", type=float, default=0.7,
                        help="apply threshold when --apply is set (default 0.7)")
    parser.add_argument("--state-dir", default=None,
                        help="override the state tree (default: Settings.state_dir)")
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
