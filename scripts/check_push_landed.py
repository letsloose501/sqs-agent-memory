"""PostToolUse hook: checks that a `git push` actually landed.

Why. A push failed with `Repository not found` and the report still said "pushed". It is a
special case of the most frequent mistake of all: claiming something was verified without
checking it by a method that could have shown the opposite. The command output was skimmed,
and the conclusion about the result was confident.

Of that whole class exactly one case can be caught mechanically: compare the local HEAD with
what is now on the remote. That is done here, trusting neither the exit code nor the output
text, and asking git again.

Input: the harness JSON on stdin. Output: 0 stays quiet, 2 warns the agent (stderr).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from _common import read_payload, utf8_stdio

DASH_C = re.compile(r"-C\s+(\"[^\"]+\"|'[^']+'|\S+)")

# A plain substring "git push" is not enough: `-C <path>`, `--no-pager`, `-c user.name=...`
# get in between. `git -C <path> push` is the most common form, and the naive check missed
# exactly it. Look for `git` and a separate word `push` inside one command.
GIT_PUSH = re.compile(r"\bgit\b[^|;&\n]*?\bpush\b")


def repo_of(command: str, cwd: str) -> Path | None:
    """Where the push ran: an explicit -C, or the call's working directory."""
    m = DASH_C.search(command)
    raw = m.group(1).strip("\"'") if m else cwd
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_dir() else None


def git(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=60)
    return r.returncode, (r.stdout or "").strip()


def main() -> int:
    utf8_stdio()
    payload = read_payload()
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not GIT_PUSH.search(command or "") or "--dry-run" in command:
        return 0

    repo = repo_of(command, str(payload.get("cwd") or ""))
    if repo is None:
        return 0
    code_local, local = git(repo, "rev-parse", "HEAD")
    if code_local != 0 or not local:
        return 0
    code_br, branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if code_br != 0 or not branch or branch == "HEAD":
        return 0

    # Ask the remote itself, not the remote-tracking ref: that one can move locally even
    # when the push failed.
    code_rem, out = git(repo, "ls-remote", "origin", f"refs/heads/{branch}")
    if code_rem != 0:
        print(f"push: could not ask origin about {branch} - check yourself whether it "
              f"landed ({out[:120]})", file=sys.stderr)
        return 2
    remote = out.split()[0] if out else ""
    if remote == local:
        return 0

    print(
        "The push did NOT land: origin is in a different state.\n"
        f"  branch   : {branch}\n"
        f"  local    : {local[:12]}\n"
        f"  on origin: {remote[:12] or '(no such branch)'}\n"
        "\n"
        "Do not report it as pushed. Read the push output in full; the usual causes are\n"
        "Repository not found, a non-fast-forward rejection, a missing upstream.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
