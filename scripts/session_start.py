"""SessionStart hook: puts the rules and, after a compaction, the working state back into context.

On every session start it prints the memory rules (`claude/rules.md` in the memory
repository). A plugin cannot add to CLAUDE.md, and a CLAUDE.md inside a plugin is not
loaded, so this hook is how the rules reach every session. SessionStart stdout with exit
code 0 is added to the context.

After a compaction (matcher `compact`) it also prints what the summary tends to drop: gate
markers not yet checked, vault notes touched in the last hours, uncommitted edits in the
memory. PreCompact cannot help here: it runs before and returns nothing to the context.

What is not here: the substance of the conversation. The hook knows files, not intent; a
task that lived only in chat is still eaten by the compaction.

Always exits 0: a hook that breaks session start is worse than none.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from _common import memory_dir, plugin_data, read_payload, utf8_stdio, vault_dir

FRESH_HOURS = 12
MAX_FILES = 8
MAX_STATUS = 6
SKIP_PARTS = {".obsidian", ".trash", ".git", "Excalidraw"}


def git_status(repo: Path | None) -> list[str]:
    if repo is None or not (repo / ".git").exists():
        return []
    try:
        proc = subprocess.run(["git", "-C", str(repo), "status", "--short"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()] if proc.returncode == 0 else []
    head = lines[:MAX_STATUS]
    if len(lines) > MAX_STATUS:
        head.append(f"   ... and {len(lines) - MAX_STATUS} more")
    return head


def recent_notes(root: Path | None) -> list[str]:
    if root is None or not root.is_dir():
        return []
    cutoff = time.time() - FRESH_HOURS * 3600
    found: list[tuple[float, str]] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        if set(rel.parts) & SKIP_PARTS:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            found.append((mtime, str(rel).replace(os.sep, "/")))
    found.sort(reverse=True)
    out = [name for _, name in found[:MAX_FILES]]
    if len(found) > MAX_FILES:
        out.append(f"... and {len(found) - MAX_FILES} more")
    return out


def pending_markers() -> list[str]:
    out = []
    d = plugin_data()
    vault_mark = d / "vault-pending.txt"
    if vault_mark.is_file():
        n = len([x for x in vault_mark.read_text(encoding="utf-8").splitlines() if x.strip()])
        if n:
            out.append(f"notes waiting for the link check: {n} (verify_vault.py)")
    return out


def block(title: str, lines: list[str]) -> list[str]:
    return [f"{title}:"] + [f"  {ln}" for ln in lines] if lines else []


def main() -> int:
    utf8_stdio()
    payload = read_payload()
    mem = memory_dir()

    if mem is None:
        print("agent-memory is installed but not configured: run /agent-memory:setup.")
        return 0
    rules = mem / "claude" / "rules.md"
    if rules.is_file():
        print(rules.read_text(encoding="utf-8", errors="replace").strip())
        print()

    if payload.get("source") != "compact":
        return 0
    parts: list[str] = []
    parts += block("Unfinished", pending_markers())
    parts += block(f"Vault notes touched in the last {FRESH_HOURS} h", recent_notes(vault_dir()))
    parts += block("Uncommitted in memory", git_status(mem))
    if parts:
        print("State at compaction time (read from disk, not from the conversation):")
        print("\n".join(parts))
        print("The task itself is not restored here: if it lived only in chat, ask again.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - never break session start
        raise SystemExit(0)
