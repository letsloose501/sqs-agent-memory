"""PreToolUse hook: blocks a long heredoc in Bash.

Why a hook and not a written rule. "A heredoc breaks on a long body" was written down as a
rule and still got broken for weeks, because a written rule is passive: it sits there and
does not fire at the moment of the action. A rule that must hold every time is a gate.

Exactly one thing breaks: a heredoc with a long mixed body (code + prose + quotes +
backslashes). A level of escaping is lost silently and garbage lands in the file, or the
command dies with `unexpected EOF`. A short heredoc of a few trivial lines is safe and passes.

Input: the harness JSON on stdin. Output: exit 0 lets the call through, exit 2 blocks it
(stderr goes to the agent as the explanation).
"""
from __future__ import annotations

import re
import sys

from _common import read_payload, utf8_stdio

MAX_BODY_LINES = 5

# <<EOF, <<-EOF, <<'PY', <<"SH" with any delimiter word
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

HINT = (
    "Blocked: a long heredoc in Bash.\n"
    "\n"
    "With a body of {n} lines a heredoc loses a level of escaping and silently writes "
    "garbage (or fails with 'unexpected EOF').\n"
    "\n"
    "Do this instead: write the script to a file with the Write tool, then run the file.\n"
    "  Write -> <scratchpad>/script.py\n"
    "  Bash  -> python \"<scratchpad>/script.py\"\n"
    "\n"
    "A short heredoc (up to {max} lines, no quotes or backslashes) is still fine."
)


def body_line_count(command: str, delimiter: str) -> int:
    """How many lines the heredoc body has before the delimiter line."""
    lines = command.splitlines()
    for i, line in enumerate(lines):
        if HEREDOC_RE.search(line):
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == delimiter:
                    return j - i - 1
            return len(lines) - i - 1  # no delimiter found: count everything to the end
    return 0


def main() -> int:
    utf8_stdio()
    payload = read_payload()
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    m = HEREDOC_RE.search(command or "")
    if not m:
        return 0
    n = body_line_count(command, m.group(2))
    if n <= MAX_BODY_LINES:
        return 0
    print(HINT.format(n=n, max=MAX_BODY_LINES), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
