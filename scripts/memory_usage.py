"""Which memory entries the agent actually opens, counted from session transcripts.

    python memory_usage.py --memory <memory_dir>                 # last 30 days, report to stdout
    python memory_usage.py --memory <memory_dir> --days 60 --out FILE
    python memory_usage.py --memory <memory_dir> --bulk 25       # sessions opening more entries are sweeps

Why. Every other measure here looks at memory from the writing side: recall on a reference set,
stale dates, index size. None says whether an entry is ever used. Two research lines name that
gap: ACE (Zhang et al., "Agentic Context Engineering", arXiv 2510.04618) keeps a counter on
every playbook bullet of how often it helped and prunes by it instead of rewriting the whole
context; REALM ("Retrieval-Driven Memory Reconsolidation", arXiv 2609.16053) reorganises memory
from retrieval feedback rather than only when new facts arrive. The transcripts already hold
the feedback: each time an entry is opened, the tool call is there. This script turns them into
a per-entry count, so memory-review decides what stays in MEMORY.md (loaded whole into every
session, with a ceiling) from use, not from a feeling.

What counts as a use (one per session per entry, whatever the number of reads):
  * Read of a file under the memory folder, or under Claude Code's own
    `~/.claude/projects/<project>/memory/` (a junction to the same repository is common);
  * `memory_recall.py read <name>`;
  * cat / sed / head / tail / Get-Content of an entry path in a Bash or PowerShell command.
Writes and edits are not uses. Sessions that open more than --bulk distinct entries are
sweeps (the weekly review, an audit) and are reported apart: they read everything by design.

What it cannot see:
  * the index line itself doing the work. A feedback entry whose index line is the whole rule
    ("no em dashes") is used every session and opened never. Cold is a question, not a verdict;
    the report marks feedback and user entries for that reason;
  * entries injected by file_context.py (PreToolUse on Read): they arrive as hook context, not
    as a tool call;
  * transcripts Claude Code already deleted (cleanupPeriodDays, 30 by default).

Exit code 0 always: it is a report for memory-review, not a gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

RECALL_READ = re.compile(r"memory_recall\.py\W+read\s+([\w.-]+)")
SHELL_READ = re.compile(
    r"(?:\bcat|\bsed\s+-n\s+\S+|\bhead(?:\s+-\S+)*|\btail(?:\s+-\S+)*|Get-Content)\s+"
    r"[\"']?([^\s\"'|;>]+\.md)")
LINK = re.compile(r"\]\(([^)]+\.md)\)")
WIKI = re.compile(r"\[\[([^\]|#]+)")
CD = re.compile(r"\bcd\s+[\"']?([^\s\"'&;|]+)")
# Claude Code's per-project memory folder: whatever it points at, a read there is a memory read.
CC_MEMORY = re.compile(r"^.*?/\.claude/projects/[^/]+/memory/")


def norm(path: str) -> str:
    return unicodedata.normalize("NFC", path.replace("\\", "/")).lower()


class Usage:
    def __init__(self, memory: Path, projects: Path):
        self.memory = memory
        self.projects = projects
        self.root = norm(str(memory.resolve())) + "/"

    def entry_of(self, path: str) -> str | None:
        """Memory-relative path of an entry file, or None when the path is not one."""
        p = norm(path)
        home = norm(str(Path.home()))
        p = re.sub(r"^~", home, p)
        p = re.sub(r"^\$env:userprofile", home, p)
        p = re.sub(r"^/([a-z])/", r"\1:/", p)
        if p.startswith(self.root):
            rel = p[len(self.root):]
        else:
            m = CC_MEMORY.match(p)
            if not m:
                return None
            rel = p[m.end():]
        if rel.endswith(".md") and not rel.startswith(("mistakes/", "scripts/", "claude/", "eval/")):
            return rel
        return None

    def uses_in_call(self, name: str, inp: dict) -> set[str]:
        found: set[str] = set()
        if name == "Read":
            e = self.entry_of(str(inp.get("file_path", "")))
            if e:
                found.add(e)
        elif name in ("Bash", "PowerShell"):
            cmd = str(inp.get("command", ""))
            for m in RECALL_READ.finditer(cmd):
                found.add(m.group(1).lower().removesuffix(".md") + ".md")
            cwd = next((m.group(1).rstrip("/\\") for m in CD.finditer(cmd)), "")
            for m in SHELL_READ.finditer(cmd):
                target = m.group(1)
                # `cd <memory> && cat x.md`: a bare name is relative to that cd
                e = self.entry_of(target) or (self.entry_of(cwd + "/" + target) if cwd else None)
                if e:
                    found.add(e)
        return found

    def scan(self, days: int) -> tuple[dict[str, dict[str, str]], int]:
        """session id -> {entry: last date}. Window by timestamps inside the file, not mtime."""
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
        sessions: dict[str, dict[str, str]] = defaultdict(dict)
        files = 0
        for f in self.projects.glob("*/*.jsonl"):
            if "evals" in f.parent.name:
                continue  # generated routing runs, not work
            files += 1
            try:
                lines = f.open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            with lines:
                for line in lines:
                    if '"tool_use"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = str(rec.get("timestamp", ""))
                    if ts < since:
                        continue
                    content = (rec.get("message") or {}).get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            for e in self.uses_in_call(str(block.get("name")), block.get("input") or {}):
                                if ts[:10] > sessions[f.stem].get(e, ""):
                                    sessions[f.stem][e] = ts[:10]
        return sessions, files

    def entries(self) -> dict[str, str]:
        """Memory-relative path -> type, for every entry in the root and in projects/."""
        out = {}
        for f in list(self.memory.glob("*.md")) + list(self.memory.glob("projects/*/*.md")):
            if f.name in ("MEMORY.md", "README.md", "SCOPES.md"):
                continue
            head = f.read_text(encoding="utf-8", errors="replace")[:600]
            m = re.search(r"^\s*type:\s*(\w+)", head, re.M)
            out[norm(str(f.relative_to(self.memory)))] = m.group(1) if m else "?"
        return out

    def index_text(self) -> str:
        f = self.memory / "MEMORY.md"
        return f.read_text(encoding="utf-8") if f.exists() else ""

    def indexed(self) -> set[str]:
        """Entries reachable from MEMORY.md: linked there, or linked from a hub it links."""
        direct = {norm(m) for m in LINK.findall(self.index_text())}
        reach = set(direct)
        for hub in (e for e in direct if e.startswith("hub-")):
            f = self.memory / hub
            if f.exists():
                body = f.read_text(encoding="utf-8", errors="replace")
                reach |= {norm(w.strip()) + ".md" for w in WIKI.findall(body)}
                reach |= {norm(m) for m in LINK.findall(body)}
        return reach

    def report(self, days: int, bulk: int) -> str:
        sessions, files = self.scan(days)
        sweeps = {s for s, used in sessions.items() if len(used) > bulk}
        count: dict[str, int] = defaultdict(int)
        last: dict[str, str] = {}
        for sid, used in sessions.items():
            if sid in sweeps:
                continue
            for e, day in used.items():
                count[e] += 1
                last[e] = max(last.get(e, ""), day)
        known = self.entries()
        in_index = self.indexed()
        # Cold candidates are lines of MEMORY.md itself: that is the file every session pays for.
        root_index = {norm(m) for m in LINK.findall(self.index_text()) if "/" not in m}

        out = [f"# Memory usage, last {days} days",
               "",
               f"Transcripts scanned: {files}. Sessions that opened an entry: {len(sessions) - len(sweeps)} "
               f"(+{len(sweeps)} sweeps over {bulk} entries, not counted).",
               "A use = an entry opened in a session (Read, memory_recall read, cat/sed/head). "
               "Index lines read at session start are invisible here.",
               ""]

        hot = sorted((e for e in count if e in known), key=lambda e: (-count[e], e))
        out += ["## Most opened", ""]
        out += [f"- {count[e]:>3}  {e}  (last {last[e]}){'' if e in in_index else '  NOT IN INDEX'}"
                for e in hot[:15]] or ["- none"]

        missing = [e for e in hot if e not in in_index and "/" not in e and count[e] >= 2]
        out += ["", "## Opened in 2+ sessions but not linked from MEMORY.md", ""]
        out += [f"- {count[e]}  {e}" for e in missing] or ["- none"]

        def hub_used(hub: str) -> bool:
            # A hub is a router: its children opened directly still mean the line pays its way.
            body = (self.memory / hub).read_text(encoding="utf-8", errors="replace")
            return any(count.get(norm(m), 0) for m in LINK.findall(body)) or \
                any(count.get(norm(w.strip()) + ".md", 0) for w in WIKI.findall(body))

        cold = sorted(e for e in root_index if e in known and count.get(e, 0) == 0
                      and not (e.startswith("hub-") and hub_used(e)))
        out += ["", f"## In the index, opened in no session ({len(cold)})", "",
                "Candidates to fold into a hub or drop to recall-only. feedback/user entries may live",
                "on their index line alone: judge those by the line, not by this count.", ""]
        out += [f"- {e}  [{known[e]}]" for e in cold] or ["- none"]

        ghosts = sorted(e for e in count if e not in known)
        if ghosts:
            out += ["", "## Opened but no longer exists (renamed or deleted)", ""]
            out += [f"- {count[e]}  {e}" for e in ghosts]
        return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-entry use counts from session transcripts.")
    ap.add_argument("--memory", type=Path, required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--bulk", type=int, default=25,
                    help="a session opening more distinct entries is a sweep (default 25)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--projects", type=Path, default=Path.home() / ".claude" / "projects",
                    help="transcripts root (default ~/.claude/projects)")
    args = ap.parse_args(argv)
    text = Usage(args.memory, args.projects).report(args.days, args.bulk)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
