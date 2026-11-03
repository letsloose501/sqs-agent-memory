"""Monthly memory review: does memory work, or does it only pile up.

    python monthly_review.py --memory <memory_dir>             # last 30 days
    python monthly_review.py --memory <memory_dir> --days 90
    python monthly_review.py --memory <memory_dir> --dry       # do not append to monthly.tsv

memory_eval.py measures search: can an entry be found. That is a state, not a benefit. The
question it does not answer: **does the agent step on an already recorded pitfall less often.**
This script counts exactly that. The source is git history, because memory-review empties
`mistakes/` every week while `git log` keeps every entry ever added there. The key number:

    repeat share = mistakes similar to one recorded EARLIER / all mistakes of the period

Falling: memory works, the lesson gets through. Flat or rising: entries are written but do not
fire, and the cure is not another entry but the next step up (a rule, then a hook), as the
memory-review ladder says.

Exit code 0 always: a report, not a gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

STOP = {
    "this", "that", "with", "from", "when", "what", "which", "into", "then", "than", "have",
    "were", "been", "does", "should", "would", "mistake", "pattern", "because",
    "это", "как", "что", "для", "при", "или", "его", "она", "они", "был", "была",
    "если", "чтобы", "надо", "нужно", "ошибка", "почему", "решение", "паттерн",
}

# The threshold was measured, not picked by eye (12.09.2026, on a real journal):
#   the same pitfall retold in other words   0.20
#   two different pitfalls                   0.02
# A tenfold gap, so 0.12 separates them with margin on both sides. The first value, 0.25,
# caught NOTHING: the metric always printed 0 and looked perfect. Changing the journal format
# means measuring the threshold again, not fitting it.
SIMILAR_ENOUGH = 0.12


class History:
    def __init__(self, memory: Path):
        self.memory = memory

    def git(self, *args: str) -> str:
        r = subprocess.run(["git", "-C", str(self.memory), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""

    def mistakes(self) -> list[tuple[dt.date, str, str]]:
        """(date, file name, text) for every entry ever added to mistakes/."""
        out: list[tuple[dt.date, str, str]] = []
        log = self.git("log", "--diff-filter=A", "--name-only", "--date=short",
                       "--format=%H|%ad", "--", "mistakes/")
        commit = when = None
        for line in log.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line and len(line.split("|")[0]) == 40:
                commit, ds = line.split("|", 1)
                when = dt.date.fromisoformat(ds)
            elif line.startswith("mistakes/") and not line.endswith(".gitkeep") and commit and when:
                out.append((when, Path(line).name, self.git("show", f"{commit}:{line}")))
        out.sort(key=lambda r: r[0])
        return out

    def rule_commits(self, since: dt.date) -> int:
        """Commits that changed the rules: the step a repeated mistake should climb to."""
        log = self.git("log", f"--since={since}", "--format=%H", "--", "claude/rules.md")
        return len(log.split())


def terms(text: str) -> set[str]:
    """Content words of an entry: they recognise one pitfall worded differently."""
    words = re.findall(r"[a-zA-Zа-яёА-ЯЁ_-]{4,}", text.lower())
    return {w for w in words if w not in STOP}


def repeat_share(records: list[tuple[dt.date, str, str]], since: dt.date) -> tuple[int, int, list[str]]:
    """How many mistakes of the period resemble one recorded before them."""
    earlier = [(n, terms(b)) for d, n, b in records if d < since]
    period = [(n, terms(b)) for d, n, b in records if d >= since]
    repeats: list[str] = []
    seen: list[tuple[str, set[str]]] = []
    for name, t in period:
        for prev_name, prev_t in earlier + seen:
            union = t | prev_t
            if union and len(t & prev_t) / len(union) >= SIMILAR_ENOUGH:
                repeats.append(f"{name}  ~  {prev_name}")
                break
        seen.append((name, t))
    return len(repeats), len(period), repeats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Repeat share of recorded mistakes, from git history.")
    ap.add_argument("--memory", type=Path, required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    today = dt.date.today()
    since = today - dt.timedelta(days=args.days)
    hist = History(args.memory)
    n_rep, n_total, examples = repeat_share(hist.mistakes(), since)
    n_rules = hist.rule_commits(since)
    share = (n_rep / n_total * 100) if n_total else 0.0
    n_entries = len([p for p in args.memory.glob("*.md")
                     if p.name not in ("MEMORY.md", "README.md", "SCOPES.md")])

    print(f"=== Memory over {args.days} days (since {since}) ===\n")
    print(f"mistakes recorded    : {n_total}")
    print(f"of them repeats      : {n_rep}  ({share:.0f}%)   <- the number that matters"
          if n_total else "of them repeats      : not measurable, no mistakes recorded in the period")
    print(f"rule changes         : {n_rules} commit(s) to claude/rules.md")
    print(f"entries in memory    : {n_entries}")
    if examples:
        print("\nrepeats, what each new entry resembles:")
        for e in examples[:8]:
            print(f"   {e}")
    print("\nHow to read: a falling share means lessons get through. A flat one means entries are")
    print("written but do not fire: climb a step (rule, then hook), do not write another entry.")

    if not args.dry:
        monthly = args.memory / "scripts" / "monthly.tsv"
        monthly.parent.mkdir(parents=True, exist_ok=True)
        new = not monthly.exists()
        with monthly.open("a", encoding="utf-8", newline="") as fh:
            if new:
                fh.write("date\tdays\tmistakes\trepeats\trepeat_share_%\trule_commits\tentries\n")
            # No mistakes is an empty share, not 0 %: zero would read as "memory works perfectly".
            share_cell = f"{share:.0f}" if n_total else ""
            fh.write(f"{today}\t{args.days}\t{n_total}\t{n_rep}\t{share_cell}\t{n_rules}\t{n_entries}\n")
        print(f"\nappended to {monthly}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
