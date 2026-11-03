"""Facts a memory rewrite lost: numbers, dates and links that left an entry without a trace.

    python memory_preservation.py --memory <memory_dir>              # entries changed in the last 7 days
    python memory_preservation.py --memory <memory_dir> --days 30
    python memory_preservation.py --memory <memory_dir> --since <commit>

Why. Entries get rewritten: memory-review merges and retires, sessions translate or tighten
entries when they edit them anyway, the index is compacted under its ceiling. Each rewrite can
silently drop a fact. TrustMem (arXiv 2606.25161) scores every memory update on coverage,
preservation and faithfulness and reports omission and corruption as the main failures of
consolidation; ACE (arXiv 2510.04618) shows the extreme case, a context rewritten from 18,282
tokens to 122 and scoring below no context at all. Their verifiers are trained models. The
cheap, deterministic part here: the facts most worth keeping are numbers (dates, sizes, prices,
counts, versions) and links to other entries, and both survive translation unchanged. A number
or a link present before the window and absent after it is a candidate for a lost fact.

How. For each entry modified (not added, not deleted) between the last commit before the
window and HEAD, compare the body before and after, front matter excluded. Report what
disappeared. An entry that gained a retirement marker ("retired", "superseded", "outdated",
"no longer") in the same window is flagged softer: removing old values is what retiring does,
the old ones stay readable in history.

What it cannot see: a fact without a number or a link ("prefers X"), a number changed on
purpose, a fact moved to another entry (it checks the whole memory for the token and says so).

Exit codes: 0 nothing lost, 1 candidates found (a report, not a block), 2 git failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

# 12.09.2026, 2026-09-12, 20.5, 16 KB, 3.9.0, 34/34, 1:1. Single digits are list numbering noise.
NUMBER = re.compile(r"\d+(?:[.,:/-]\d+)+|\d{2,}")
LINK = re.compile(r"\[\[([^\]|#]+)\]\]|\]\(([^)]+\.md)\)")
RETIRED = re.compile(r"retired|superseded|outdated|no longer", re.I)


class Repo:
    def __init__(self, memory: Path):
        self.memory = memory

    def git(self, *args: str) -> str:
        r = subprocess.run(["git", "-C", str(self.memory), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"git {' '.join(args)} failed")
        return r.stdout

    def base_commit(self, days: int, since: str | None) -> str:
        if since:
            return since
        cutoff = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        sha = self.git("rev-list", "-1", f"--before={cutoff}", "HEAD").strip()
        if not sha:  # the window starts before history does
            sha = self.git("rev-list", "--max-parents=0", "HEAD").split()[0]
        return sha

    def check(self, base: str) -> list[str]:
        changed = self.git("diff", "--name-status", "--no-renames", base, "HEAD", "--", "*.md")
        whole = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                          for p in self.memory.rglob("*.md") if ".git" not in p.parts)
        lines = []
        for row in changed.splitlines():
            status, _, path = row.partition("\t")
            if status != "M" or path.startswith(("mistakes/", "scripts/")) or path == "MEMORY.md":
                continue
            before = body(self.git("show", f"{base}:{path}"))
            after = body(self.git("show", f"HEAD:{path}"))
            lost = facts(before) - facts(after)
            if not lost:
                continue
            retired = bool(RETIRED.search(after)) and not RETIRED.search(before)
            # "16" or "443" occurs somewhere in any memory; finding it elsewhere says nothing.
            moved = sorted(t for t in lost if t in whole and not re.fullmatch(r"\d{2,3}", t))
            gone = sorted(t for t in lost if t not in whole)
            tag = "  (retired in this window: expected)" if retired else ""
            lines.append(f"- {path}{tag}")
            if gone:
                lines.append(f"    gone from all memory: {', '.join(gone)}")
            if moved:
                lines.append(f"    left this entry, still elsewhere: {', '.join(moved)}")
        return lines


def body(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def facts(text: str) -> set[str]:
    out = set(NUMBER.findall(text))
    out |= {"[[" + (a or b.removesuffix(".md")).strip() + "]]" for a, b in LINK.findall(text)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Numbers and links lost by memory rewrites.")
    ap.add_argument("--memory", type=Path, required=True)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--since", help="compare from this commit instead of a date window")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    repo = Repo(args.memory)
    try:
        base = repo.base_commit(args.days, args.since)
        lines = repo.check(base)
    except (RuntimeError, OSError, IndexError) as e:
        print(f"git failed: {e}", file=sys.stderr)
        return 2
    window = f"since {args.since}" if args.since else f"last {args.days} days"
    print(f"# Facts lost by rewrites, {window} (base {base[:8]})\n")
    if not lines:
        print("Nothing lost: every number and link of a modified entry is still in it.")
        return 0
    print("Check each with `git diff <base> HEAD -- <entry>`: put back what was lost by accident,")
    print("leave what was retired or corrected on purpose.\n")
    print("\n".join(lines))
    return 1


if __name__ == "__main__":
    sys.exit(main())
