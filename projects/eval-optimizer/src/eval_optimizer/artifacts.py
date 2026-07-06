"""Generator-artifact parsing (ADR-0021 extraction).

`parse_artifact` — the `# === path ===` splitter — was the one genuinely
reusable, test-backed piece of the retired Docker-validate module. Extracted to
this live home; the rest of validate.py is preserved in eval_optimizer.legacy.
"""
from __future__ import annotations

import re

_MARKER = re.compile(r"^#\s*={2,}\s*(.+?)\s*={2,}\s*$")   # "# === path/to/file.py ==="
_FENCE = re.compile(r"^\s*```")                            # markdown code fence line


def parse_artifact(text: str) -> dict[str, str]:
    """Extract {relative_path: file_content} from a generator's response.

    Splits on `# === path ===` markers; drops prose before the first marker and
    strips surrounding ``` code fences. Robust to the prose+fenced output we saw
    from the generators.
    """
    files: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []

    def _store(name: str | None, lines: list[str]) -> None:
        if not name:
            return
        body = "\n".join(line for line in lines if not _FENCE.match(line)).strip()
        files[name] = (body + "\n") if body else ""

    for line in text.splitlines():
        m = _MARKER.match(line)
        if m:
            _store(current, buf)
            current, buf = m.group(1).strip(), []
        elif current is not None:
            buf.append(line)
    _store(current, buf)
    return files
