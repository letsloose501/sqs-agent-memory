"""Deterministic pre-sort of the mistakes journal for the weekly memory review.

    python journal_reflect.py --memory <memory_dir>              groups, steps, dead ends
    python journal_reflect.py --memory <memory_dir> --out FILE   also write the report

Why. The weekly review groups journal entries by substance and moves repeats one step up
(once: leave it, twice: a rule, three times: a hook). Grouping by a model each week costs
tokens and is not reproducible; this does the mechanical part the same way every run, and the
model only judges the result. The design follows graphify's `reflect` (no LLM, stable output,
signals time-decayed so a fresh repeat outweighs an old one, nothing promoted on one signal).

What it does:
  * parses entries in either field set: MISTAKE/WHY/FIX/PATTERN or the Russian
    ОШИБКА/ПОЧЕМУ/РЕШЕНИЕ/ПАТТЕРН, plus an optional KIND: mistake | dead_end;
  * tags each mistake with failure classes by keywords in both languages (the classes
    mirror the working rules: verification, numbers, sources, escaping, repository state,
    probes, privacy, rendered output) and groups by the strongest class. Plain word overlap
    was tried first and found no group at all in a real 23-entry journal: entries are in two
    languages and the same lesson is never worded the same way twice. Classes are
    overridable with <memory>/claude/lesson-classes.json ({"class": ["keyword", ...]});
  * proposes the step from the number of DISTINCT DAYS in a group, not entries, so one bad
    afternoon logged three times does not look like a habit;
  * names the existing rule a group most resembles: a repeat of something already in
    claude/rules.md means the rule did not work, and the next step is a hook, not a new rule;
  * lists dead ends separately: approaches that were tried and failed, not to be re-derived.

What it cannot do: understand an entry. A keyword class is a pre-sort; an entry that uses
none of the keywords lands in "unclassified", and the review reads every group and may move
entries between them.

Exit 0 always (it is a report), 2 if the memory folder or journal is missing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

FIELDS = {
    "mistake": ("MISTAKE", "ОШИБКА"),
    "why": ("WHY", "ПОЧЕМУ"),
    "fix": ("FIX", "РЕШЕНИЕ"),
    "pattern": ("PATTERN", "ПАТТЕРН"),
    "kind": ("KIND", "ТИП"),
}
HALF_LIFE_DAYS = 30
CLASSES = {
    "verification": ["verified", "checked", "matches", "match", "claim", "confirm", "prove", "made sure",
                     "artifact", "проверил", "проверк", "сверил", "совпад", "заявил", "подтверд", "удостовер"],
    "numbers": ["number", "figure", "value", "hex", "price", "estimate", "plausible", "invented", "count",
                "число", "цифр", "правдоподоб", "выдум", "оценк"],
    "sources": ["source", "summary", "quote", "cited", "webfetch", "websearch", "retold", "carried",
                "источник", "цитат", "пересказ", "сводк"],
    "shell-escaping": ["heredoc", "escape", "backslash", "quoting", "msys", "uri", "-c string",
                       "экраниров", "слэш", "кавычк"],
    "repository-state": ["commit", "push", "git status", "uncommitted", "remote", "sync", "working tree",
                         "коммит", "пуш", "git"],
    "probes-and-tools": ["probe", "self-check", "selfcheck", "marker", "dump", "timeout", "tool",
                         "маркер", "проб", "инструмент", "self-check"],
    "privacy": ["email", "personal", "user-agent", "private", "личн", "почт", "персональ"],
    "rendered-output": ["render", "pdf", "glyph", "font", "png", "frame", "mask", "рендер", "шрифт",
                        "глиф", "кадр"],
}
STOP = set("""the and for that this with from not was are but you your into when what which then than
have has had its it's been being were they them their there here also only just like more most
some such very will would should could about after before other over same each every does did
done make made using used use one two out all any can cannot don't didn't isn't wasn't
это как что для при или его она они был была было были без над под так там тут уже ещё еще
если чтобы когда потом потому только тоже этот эта эти того тем чем ним них него неё всё все
""".split())
WORD_RE = re.compile(r"[a-zа-яё][a-zа-яё0-9_]{3,}", re.I)


def stems(text: str) -> set[str]:
    return {w.lower()[:6] for w in WORD_RE.findall(text) if w.lower() not in STOP}


def parse(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    entry = {"file": path.name}
    for key, labels in FIELDS.items():
        rx = re.compile(r"^(?:" + "|".join(labels) + r"):\s*(.*?)(?=^\s*(?:[A-ZА-ЯЁ]{3,}):|\Z)", re.M | re.S)
        m = rx.search(text)
        entry[key] = " ".join(m.group(1).split()) if m else ""
    if not (entry["mistake"] or entry["pattern"]):
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    entry["date"] = dt.date.fromisoformat(m.group(1)) if m else None
    entry["kind"] = "dead_end" if "dead" in entry["kind"].lower() or "тупик" in entry["kind"].lower() else "mistake"
    entry["stems"] = stems(entry["pattern"] + " " + entry["mistake"])
    return entry


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def load_classes(mem: Path) -> dict[str, list[str]]:
    custom = mem / "claude" / "lesson-classes.json"
    if custom.is_file():
        try:
            import json
            data = json.loads(custom.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return {str(k): [str(x).lower() for x in v] for k, v in data.items()}
        except ValueError:
            print(f"warning: {custom} is not valid JSON; using the built-in classes", file=sys.stderr)
    return CLASSES


def classify(entry: dict, classes: dict[str, list[str]]) -> dict[str, int]:
    """Keyword hits per class in PATTERN, MISTAKE and WHY (the pattern counts double)."""
    pat = entry["pattern"].lower()
    rest = (entry["mistake"] + " " + entry["why"]).lower()
    hits = {}
    for name, words in classes.items():
        n = sum(2 * pat.count(w) + rest.count(w) for w in words)
        if n:
            hits[name] = n
    return hits


def group_by_class(entries: list[dict], classes: dict[str, list[str]]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for e in entries:
        e["classes"] = classify(e, classes)
        top = max(e["classes"], key=lambda k: (e["classes"][k], k)) if e["classes"] else "unclassified"
        groups.setdefault(top, []).append(e)
    return groups


def rules_index(mem: Path) -> list[tuple[str, set[str]]]:
    rules = mem / "claude" / "rules.md"
    if not rules.is_file():
        return []
    out, head, body = [], None, []
    for line in rules.read_text(encoding="utf-8", errors="replace").splitlines() + ["## "]:
        if line.startswith("## "):
            if head:
                out.append((head, stems(head + " " + " ".join(body))))
            head, body = line[3:].strip(), []
        else:
            body.append(line)
    return [(h, s) for h, s in out if h]


def weight(d: dt.date | None, today: dt.date) -> float:
    if d is None:
        return 0.5
    return 0.5 ** (max((today - d).days, 0) / HALF_LIFE_DAYS)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    journal = a.memory.expanduser() / "mistakes"
    if not journal.is_dir():
        print(f"no journal at {journal}", file=sys.stderr)
        return 2
    today = dt.date.today()
    entries = [e for e in (parse(p) for p in sorted(journal.glob("*.md"))) if e]
    mistakes = [e for e in entries if e["kind"] == "mistake"]
    dead = [e for e in entries if e["kind"] == "dead_end"]
    rules = rules_index(a.memory.expanduser())

    by_class = group_by_class(mistakes, load_classes(a.memory.expanduser()))

    def score(item: tuple[str, list[dict]]) -> tuple:
        name, g = item
        days = len({e["date"] for e in g})
        return (name == "unclassified", -days, -sum(weight(e["date"], today) for e in g), name)

    ordered = sorted(by_class.items(), key=score)
    groups = [g for _, g in ordered]
    lines = [f"# Journal pre-sort ({today.isoformat()})", "",
             f"{len(mistakes)} mistake entries in {len(groups)} group(s), {len(dead)} dead end(s). "
             f"Groups by keyword class: read each before acting; move entries as the substance says.", ""]
    for n, (name, g) in enumerate(ordered, 1):
        days = len({e["date"] for e in g})
        step = "leave it (seen once)" if days <= 1 else ("a rule" if days == 2 else "a hook (or a gate in a script)")
        if name == "unclassified":
            step = "read each: no keyword class matched"
        w = sum(weight(e["date"], today) for e in g)
        lines.append(f"## {n}. {name}: {len(g)} entr{'y' if len(g) == 1 else 'ies'}, {days} distinct day(s), "
                     f"weight {w:.2f}: step {step}")
        if rules:
            best = max(rules, key=lambda r: jaccard(r[1], set().union(*(e["stems"] for e in g))))
            sim = jaccard(best[1], set().union(*(e["stems"] for e in g)))
            if sim >= 0.05:
                lines.append(f"closest existing rule: \"{best[0]}\" (overlap {sim:.2f}); "
                             "if it already covers this, the rule did not work: go one step up")
        for e in g:
            also = [k for k in e["classes"] if k != name]
            lines.append(f"- {e['file']}: {(e['pattern'] or e['mistake'])[:200]}"
                         + (f"  [also: {', '.join(also)}]" if also else ""))
        lines.append("")
    if dead:
        lines += ["## Dead ends: tried and failed, do not re-derive", ""]
        for e in sorted(dead, key=lambda e: e["file"]):
            lines.append(f"- {e['file']}: {(e['mistake'] or e['pattern'])[:220]}")
        lines.append("")
    report = "\n".join(lines)
    print(report)
    if a.out:
        a.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
