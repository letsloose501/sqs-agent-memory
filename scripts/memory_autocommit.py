"""Stop hook: commit changes in the agent memory repository, if there are any.

Silent when nothing changed, otherwise history fills up with empty commits. Pushes to the
remote when one is set and the `memory_autopush` option is on.

Why a hook and not "remember to commit": a manual commit is forgotten exactly the time the
edit mattered, and every memory edit being a commit is what makes any edit reversible
(`git log -p`, `git revert`).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date

from _common import flag, memory_dir, utf8_stdio


def git(mem, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(mem), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    utf8_stdio()
    mem = memory_dir()
    if mem is None or not (mem / ".git").is_dir():
        return 0  # not configured or not a repository: nothing for this hook to do

    status = git(mem, "status", "--porcelain")
    if status.returncode != 0 or not status.stdout.strip():
        return 0

    files = [line[3:] for line in status.stdout.splitlines() if line[3:]]
    head = ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")

    git(mem, "add", "-A")
    commit = git(mem, "commit", "-m", f"memory {date.today().isoformat()}: {head}")
    if commit.returncode != 0:
        # Most often: git user.name / user.email not set. The hook must not break the session.
        print("memory-autocommit: commit failed - " + (commit.stderr or commit.stdout).strip()[:300],
              file=sys.stderr)
        return 0

    # Local git protects against a bad edit, not against a dead disk; the remote does.
    # The remote must be private: memory holds personal facts about the user.
    if flag("memory_autopush", True) and git(mem, "remote").stdout.strip():
        push = git(mem, "push")
        if push.returncode != 0:
            print("memory-autocommit: committed locally, push failed - "
                  + push.stderr.strip()[:300], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
