"""PreToolUse guard: deny raw global pip installs (AgenticWork policy).

Hardened per ADR-0022 (crit-pip-hook): the decision is made from the parsed
argv of each shell segment — program plus subcommand — never from substring
hints, so a trailing comment or quoted mention can no longer waive a denial
(the old ALLOW_HINTS waiver let `pip install requests  # .venv` through).
`uv pip install` passes because the tokenized program is `uv`. A command that
cannot be tokenized falls back to the regex deny with no waiver: the hook
fails toward denial, never toward bypass.

Tested by evals/agentic-smoke/tests/test_pip_hook.py.
"""

import json
import re
import shlex
import sys

# A new command begins after any of these shell separators (POSIX + PowerShell).
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|&\n]")

# Tokenization-failure fallback: deny on the raw pattern, with no allow-waiver.
BLOCK_PATTERNS = [
    re.compile(r"(?i)(^|[\s;&|])pip3?\s+install\b"),
    re.compile(r"(?i)(^|[\s;&|])python3?(\.\d+)?\s+-m\s+pip\s+install\b"),
    re.compile(r"(?i)(^|[\s;&|])py\s+(-[0-9.]+\s+)?-m\s+pip\s+install\b"),
]

DENY_REASON = (
    "Raw global pip installs are blocked by AgenticWork policy. "
    "Use 'uv add', 'uv run', or a documented project .venv workflow."
)


def _extract_command(payload: object) -> str:
    if isinstance(payload, dict):
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
            return tool_input["command"]
        for key in ("command", "cmd", "script"):
            if isinstance(payload.get(key), str):
                return payload[key]
    return json.dumps(payload, sort_keys=True)


def _deny(reason: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))


def _program(token: str) -> str:
    """Basename of the invoked program, quote- and extension-insensitive."""
    name = token.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _subcommand(words: list[str]) -> str:
    """First argument that is not an option flag."""
    for word in words:
        if not word.startswith("-"):
            return word.strip("\"'").lower()
    return ""


def _is_global_pip_install(tokens: list[str]) -> bool:
    words = list(tokens)
    # Skip leading VAR=value environment assignments.
    while words and "=" in words[0] and not words[0].startswith("-"):
        words.pop(0)
    if not words:
        return False
    prog = _program(words[0])
    rest = words[1:]
    if prog.startswith("pip"):  # pip, pip3, pip3.12
        return _subcommand(rest) == "install"
    if prog.startswith("python") or prog == "py":  # python -m pip / py -3.12 -m pip
        for i, word in enumerate(rest):
            if word == "-m":
                module = rest[i + 1].strip("\"'").lower() if i + 1 < len(rest) else ""
                return module == "pip" and _subcommand(rest[i + 2:]) == "install"
    return False


def _command_denied(command: str) -> bool:
    try:
        segments = [shlex.split(seg, posix=False) for seg in SEGMENT_SPLIT.split(command)]
    except ValueError:
        # Unparseable (e.g. unbalanced quotes): fail toward denial.
        return any(pattern.search(command) for pattern in BLOCK_PATTERNS)
    return any(_is_global_pip_install(tokens) for tokens in segments)


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": raw}

    if _command_denied(_extract_command(payload)):
        _deny(DENY_REASON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
