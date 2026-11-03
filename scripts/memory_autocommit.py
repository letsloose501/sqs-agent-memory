"""Stop hook: commit changes in the agent memory repository, if there are any.

Silent when nothing changed, otherwise history fills up with empty commits. Pushes to the
remote when one is set and the `memory_autopush` option is on, and retries an earlier push that
failed even when this turn changed nothing: commits that never left the machine are the ones a
dead disk takes with it.

Why a hook and not "remember to commit": a manual commit is forgotten exactly the time the
edit mattered, and every memory edit being a commit is what makes any edit reversible
(`git log -p`, `git revert`).

A failure is not allowed to be silent. Stderr of a Stop hook that exits 0 reaches neither the
user nor the agent, so the user would believe memory is under git while nothing is committed
(most often: no git user.name / user.email). On a failure the hook shows a `systemMessage` to
the user and leaves a marker that session_start.py prints at the next session start until a
run succeeds. It still exits 0: blocking the stop (exit 2) would make the agent retry a
commit it cannot fix, every turn.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date

from _common import flag, memory_dir, plugin_data, utf8_stdio

FAILED = "memory-autocommit-failed.txt"


def git(mem, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(mem), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def fail(what: str, proc: subprocess.CompletedProcess) -> int:
    reason = (proc.stderr or proc.stdout).strip().splitlines()
    text = f"{what}: {reason[-1] if reason else 'git exited ' + str(proc.returncode)}"
    (plugin_data() / FAILED).write_text(f"{date.today().isoformat()} {text}\n", encoding="utf-8")
    print(json.dumps({"systemMessage": f"agent-memory: {text}"}, ensure_ascii=False))
    return 0


def push(mem) -> subprocess.CompletedProcess | None:
    """Push if there is something to push. None: nothing to do."""
    remotes = git(mem, "remote").stdout.split()
    if not remotes:
        return None
    upstream = git(mem, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream.returncode != 0:
        # No upstream yet (a fresh repository): set it on the first remote, as setup intends.
        return git(mem, "push", "-u", remotes[0], "HEAD")
    ahead = git(mem, "rev-list", "--count", "@{u}..HEAD").stdout.strip()
    return git(mem, "push") if ahead not in ("", "0") else None


def main() -> int:
    utf8_stdio()
    mem = memory_dir()
    if mem is None or not (mem / ".git").is_dir():
        return 0  # not configured or not a repository: nothing for this hook to do

    status = git(mem, "status", "--porcelain")
    if status.returncode != 0:
        return fail("memory is not readable as a git repository", status)
    if status.stdout.strip():
        files = [line[3:] for line in status.stdout.splitlines() if line[3:]]
        head = ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
        git(mem, "add", "-A")
        commit = git(mem, "commit", "-m", f"memory {date.today().isoformat()}: {head}")
        if commit.returncode != 0:
            return fail("memory changes were NOT committed", commit)

    # Local git protects against a bad edit, not against a dead disk; the remote does.
    # The remote must be private: memory holds personal facts about the user.
    if flag("memory_autopush", True):
        pushed = push(mem)
        if pushed is not None and pushed.returncode != 0:
            return fail("memory committed locally, push failed", pushed)
    (plugin_data() / FAILED).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
