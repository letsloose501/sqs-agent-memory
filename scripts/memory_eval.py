"""Memory health: numbers that show a direction over time, not a feeling.

    python memory_eval.py --memory <memory_dir>          measure and append to history.tsv
    python memory_eval.py --memory <memory_dir> --dry    measure only

What is measured and why:

  index     size of MEMORY.md in lines and KB. Claude Code loads the first 200 lines or 25 KB
            of it, whichever comes first, and silently drops the rest (code.claude.com/docs/en/memory).
            The ceiling here is lower on purpose (150 lines, 20 KB): it leaves room for a
            week of growth between reviews. Over the ceiling the script exits 1, because a
            number nothing reacts to changes no behaviour.
  orphans   entry files with no line in MEMORY.md (never recalled) and index lines pointing
            at no file (recalled into nothing).
  no-desc   entries without a `description`: an entry is recalled by it.
  stale     entries with a promise dated in the past (a deadline, a reminder, a window) and
            no "retired" mark. Relying on an outdated fact is worse than not knowing it.
  source    entries stated by the user, observed in work, inferred by the agent, or with no
            source yet. Inferred entries are hypotheses until confirmed.

"Not measured" is not zero: a metric that could not be read prints as such and is written
as an empty field, and the exit code is 2.

Exit codes: 0 measured and within ceilings, 1 index over the ceiling, 2 something not measured.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

MAX_INDEX_KB = 20.0
MAX_INDEX_LINES = 150

DATE_RES = (
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                    # 2026-09-26
    re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b"),                  # 26.09.2026
)
PROMISE_RE = re.compile(r"deadline|due|remind|window|until|by \w+ \d|expires|scheduled|"
                        r"postponed|waiting for|pending|follow up|check back", re.I)
RETIRED_RE = re.compile(r"retired|no longer|superseded|obsolete|replaced by|expired", re.I)
LINK_RE = re.compile(r"\]\(([^)#]+\.md)\)")


def dates_in(text: str) -> list[dt.date]:
    out = []
    for i, rx in enumerate(DATE_RES):
        for m in rx.finditer(text):
            try:
                y, mo, d = (m.group(1), m.group(2), m.group(3)) if i == 0 else (m.group(3), m.group(2), m.group(1))
                out.append(dt.date(int(y), int(mo), int(d)))
            except ValueError:
                pass
    return out


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory", type=Path, required=True)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    mem = args.memory.expanduser()
    index = mem / "MEMORY.md"
    if not index.is_file():
        print(f"not measured: no {index}", file=sys.stderr)
        return 2

    raw = index.read_bytes()
    kb = len(raw) / 1024
    lines = raw.decode("utf-8", errors="replace").splitlines()
    linked = {Path(m).name for m in LINK_RE.findall("\n".join(lines))}
    # A hub entry (one index line listing several entries) keeps the index short; what a
    # hub links to is reachable too, one level deep.
    reachable = set(linked)
    for name in linked:
        hub = mem / name
        if hub.is_file():
            reachable |= {Path(m).name for m in LINK_RE.findall(hub.read_text(encoding="utf-8", errors="replace"))}
    special = {"memory.md", "readme.md", "scopes.md"}
    entries = [p for p in mem.glob("*.md") if p.name.lower() not in special]
    unindexed = sorted(p.name for p in entries if p.name not in reachable)
    dangling = sorted(n for n in linked if not (mem / n).exists())

    no_desc, stale = [], []
    sources = {"stated": 0, "observed": 0, "inferred": 0, "missing": 0}
    today = dt.date.today()
    for p in entries:
        text = p.read_text(encoding="utf-8", errors="replace")
        head = text[:800]
        if not re.search(r"^description:\s*\S", head, re.M):
            no_desc.append(p.name)
        m = re.search(r"^\s*source:\s*(stated|observed|inferred)\s*$", head, re.M | re.I)
        sources[m.group(1).lower() if m else "missing"] += 1
        if RETIRED_RE.search(text):
            continue
        for line in text.splitlines():
            if PROMISE_RE.search(line) and any(d < today for d in dates_in(line)):
                stale.append(p.name)
                break

    print(f"index:    {len(lines)} lines, {kb:.1f} KB "
          f"({len(lines) / MAX_INDEX_LINES * 100:.0f}% of {MAX_INDEX_LINES} lines, "
          f"{kb / MAX_INDEX_KB * 100:.0f}% of {MAX_INDEX_KB:.0f} KB)")
    print(f"entries:  {len(entries)}")
    print(f"orphans:  {len(unindexed)} not in the index, {len(dangling)} index lines without a file")
    for n in unindexed[:10]:
        print(f"            not indexed: {n}")
    for n in dangling[:10]:
        print(f"            no file:     {n}")
    print(f"no-desc:  {len(no_desc)}" + (f"  ({', '.join(no_desc[:6])})" if no_desc else ""))
    print(f"source:   stated {sources['stated']}, observed {sources['observed']}, "
          f"inferred {sources['inferred']}, missing {sources['missing']}  "
          f"(inferred entries are hypotheses: confirm or retire them)")
    print(f"stale:    {len(stale)}  (a screen, not a verdict: read each before editing)")
    for n in stale[:10]:
        print(f"            {n}")

    if not args.dry:
        hist = mem / "scripts" / "history.tsv"
        hist.parent.mkdir(exist_ok=True)
        new = not hist.exists()
        with hist.open("a", encoding="utf-8") as fh:
            if new:
                fh.write("date\tindex_lines\tindex_kb\tentries\tunindexed\tdangling\tno_desc\tstale"
                         "\tinferred\tno_source\n")
            fh.write(f"{today.isoformat()}\t{len(lines)}\t{kb:.1f}\t{len(entries)}\t{len(unindexed)}\t"
                     f"{len(dangling)}\t{len(no_desc)}\t{len(stale)}\t{sources['inferred']}\t{sources['missing']}\n")

    if kb > MAX_INDEX_KB or len(lines) > MAX_INDEX_LINES:
        print("\nThe index is over its ceiling: compact it (shorter lines, merge close entries, "
              "detail into entry bodies) instead of adding more.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
