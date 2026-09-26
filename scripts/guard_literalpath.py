"""PreToolUse hook: a PowerShell delete of a file with brackets in its name is rewritten to -LiteralPath.

The trap. In PowerShell `-Path` treats `[` and `]` as a wildcard pattern. A name such as
`Notes [1].md` matches nothing under that pattern, `Remove-Item` silently deletes zero files
and exits 0. A report of "deleted" is then false in a way that neither the output nor the
exit code can refute. One switch fixes it: `-LiteralPath` takes the name literally.

Why a rewrite and not a refusal. A refusal makes the agent retype the command and teaches
nothing: the next session writes it the same way. The hook fixes the call in place through
`updatedInput` and leaves the decision to the human (`permissionDecision: ask`).

It fires narrowly: only on a delete, only when the command has a bracket, only when
`-LiteralPath` is not there yet. A wildcard delete (`*.tmp`) is left alone: there the
pattern is wanted. Does nothing outside the PowerShell tool.

Input: the harness JSON on stdin. Output: 0 plus JSON on stdout (the rewritten call), or 2
to block when the command is compound and cannot be rewritten safely.
"""
from __future__ import annotations

import json
import re
import sys

from _common import read_payload, utf8_stdio

DELETERS = r"(?:Remove-Item|ri|rm|del|erase|rd|rmdir)"
# The command must START with the delete, so `del` inside someone else's string is not caught.
HEAD_RE = re.compile(rf"^\s*({DELETERS})\b", re.IGNORECASE)
# -LiteralPath and the abbreviations PowerShell accepts.
HAS_LITERAL_RE = re.compile(r"-(?:literalpath|literalp|litera|liter|lite|lit|li|lp)\b", re.IGNORECASE)
PATH_PARAM_RE = re.compile(r"-path\b", re.IGNORECASE)
COMPOUND_RE = re.compile(r"[|;&]|\n")

DENY_HINT = """Blocked: deleting a file with brackets in its name without -LiteralPath.

  command: {cmd}

In PowerShell `-Path` treats `[` and `]` as a pattern. A file with such brackets does not
match it: `Remove-Item` deletes ZERO files and exits 0, so "deleted" would be a lie nothing
can refute.

The command is compound (`|`, `;`, `&` or a line break), so it cannot be rewritten
automatically. Split it into separate calls and add -LiteralPath by hand. After the delete,
check that the file is really gone."""

ASK_REASON = """Rewritten to -LiteralPath: the name has brackets.

  before: {before}
  after:  {after}

`-Path` treats `[` and `]` as a pattern, the file does not match it, and the delete silently
touches zero files with exit code 0. After it runs, check that the file is really gone."""


def rewrite(command: str) -> str | None:
    m = HEAD_RE.match(command)
    if not m:
        return None
    if PATH_PARAM_RE.search(command):
        return PATH_PARAM_RE.sub("-LiteralPath", command, count=1)
    end = m.end()  # positional argument: the switch goes right after the command name
    return command[:end] + " -LiteralPath" + command[end:]


def main() -> int:
    utf8_stdio()
    payload = read_payload()
    if payload.get("tool_name") != "PowerShell":
        return 0
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command", ""))
    if not command or not HEAD_RE.match(command):
        return 0
    if "[" not in command and "]" not in command:
        return 0
    if HAS_LITERAL_RE.search(command):
        return 0

    fixed = None if COMPOUND_RE.search(command) else rewrite(command)
    if not fixed or fixed == command:
        print(DENY_HINT.format(cmd=command[:200]), file=sys.stderr)
        return 2

    # updatedInput replaces the whole object: every other field goes back unchanged.
    updated = dict(tool_input)
    updated["command"] = fixed
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": ASK_REASON.format(before=command[:160], after=fixed[:160]),
            "updatedInput": updated,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
