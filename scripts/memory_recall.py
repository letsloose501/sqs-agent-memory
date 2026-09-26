"""Find memory entries by meaning of the words, then open only what the task needs.

    python memory_recall.py recall "query" ["same query in the user's words" ...] [--limit 8]
    python memory_recall.py read <name> [--level abstract|outline|full]
    python memory_recall.py eval [--cases FILE]

Why. MEMORY.md is loaded whole into every session and has a ceiling. Past it, an entry that is
not in the index is invisible unless something can find it by content. This is that something,
and it is built so it never pastes memory into the context on its own:

  recall   answers with one line per hit: name, type, path, the entry's description and the
           line that matched. The agent decides what to open.
  read     opens one entry at the depth the task needs: `abstract` (description and source),
           `outline` (headings and the first sentence of each paragraph), `full` (the file).

Each rung costs several times more context than the one before, and each is a place to stop.

The files are the truth. The search index is built in memory on every call from the Markdown
files and thrown away on exit: there is no cache to go stale or to rebuild.

Two languages. Entries are written mostly in English, users talk in their own language. Several
queries in one call are ranked separately and fused by reciprocal rank (RRF), so the agent
passes the English wording and the user's own words together. Within a language, word forms
are matched by an English stemmer (Porter) and, for other scripts, by a shortened prefix.

Why `words` is the default mode (26.09.2026, 34 reference cases on a 150-entry memory, half the
entries still Russian): words 28/34 in the top 3, trigram 23/34 before index lines were added
and worse than words on every run, both fused 27/34. Trigram matches substrings and pulls in
noise. English-only queries on the same set scored 23/34: 7 of the 8 misses were entries written
in the other language, which is why the agent always sends both wordings. Re-measure with
`eval --mode` before changing the default.

Why wordings are fused by their best rank, not summed (the same day): summing left 2 of the 4
remaining misses ranked first by the English wording and outvoted by entries sitting third to
fifth in both lists. With the best rank: 31/34 top 3; after two descriptions were rewritten to
name what the entry is for, 33/34 (34/34 top 5). Because those two fixes were made against that
set, a held-out set written afterwards on untouched entries is the fair check: 11/12 summed,
12/12 by best rank.

Memory folder: --memory, else CLAUDE_PLUGIN_OPTION_MEMORY_DIR, else the folder above this
script when it holds a MEMORY.md (a copy kept inside the memory repository).

Exit codes: 0 found (or eval ran), 1 nothing found, 2 no memory folder or bad arguments.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

SKIP_FILES = {"memory.md", "readme.md", "scopes.md", "changelog.md"}
SKIP_DIRS = {"scripts", "claude", "eval", "node_modules", "__pycache__"}
RRF_K = 60
WORD_RE = re.compile(r"\w+", re.U)
CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
# Words that match everywhere and rank nothing. Short on purpose: a stop list that grows eats
# real terms ("run", "can" are verbs someone searches for).
STOP = set("""
a an and are as at be been by do does for from has have how i if in into is it its me my no not
of on or our so that the their them then there these they this to was we were what when where
which who why will with you your
и в во на не что как это для по из за от до ли же бы то так он она они мы вы я его её их
у к с со о об а но или если чтобы где когда почему зачем какой какая какие который
""".split())


@dataclass
class Entry:
    name: str           # path relative to the memory folder, without .md
    path: Path
    title: str = ""
    description: str = ""
    type: str = ""
    source: str = ""
    body: str = ""
    extra: dict = field(default_factory=dict)


def fold(text: str) -> str:
    """Case and the one letter the tokenizer does not fold (ё/е)."""
    return text.lower().replace("ё", "е")


def memory_folder(arg: str | None) -> Path | None:
    if arg:
        return Path(os.path.expandvars(arg)).expanduser()
    env = os.environ.get("CLAUDE_PLUGIN_OPTION_MEMORY_DIR", "").strip()
    if env:
        return Path(os.path.expandvars(env)).expanduser()
    here = Path(__file__).resolve().parent.parent
    return here if (here / "MEMORY.md").is_file() else None


def parse(path: Path, root: Path) -> Entry:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = "", text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if m:
        fm, body = m.group(1), text[m.end():]

    def field_(key: str) -> str:
        f = re.search(rf"^\s*{key}:\s*(.+?)\s*$", fm, re.M)
        return f.group(1).strip().strip("\"'") if f else ""

    rel = path.relative_to(root).with_suffix("").as_posix()
    desc = field_("description")
    if not desc:  # entries without frontmatter (a journal line): the first non-empty line
        desc = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")[:200]
    return Entry(name=rel, path=path, title=field_("name") or path.stem, description=desc,
                 type=field_("type") or ("mistake" if rel.startswith("mistakes/") else ""),
                 source=field_("source"), body=body)


INDEX_LINE_RE = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)#]+\.md)\)\s*(.*)$")


def index_lines(root: Path) -> dict[str, str]:
    """Each index's own line for an entry (title and hook): a summary someone wrote by hand,
    often in other words than the entry. Keyed by the entry's path relative to the root."""
    out: dict[str, str] = {}
    for idx in root.rglob("MEMORY.md"):
        if any(x.startswith(".") for x in idx.relative_to(root).parts):
            continue
        for line in idx.read_text(encoding="utf-8", errors="replace").splitlines():
            m = INDEX_LINE_RE.match(line)
            if m:
                target = (idx.parent / m.group(2)).resolve()
                try:
                    key = target.relative_to(root.resolve()).with_suffix("").as_posix()
                except ValueError:
                    continue
                out[key] = f"{m.group(1)} {m.group(3).lstrip('-— ')}"
    return out


def load(root: Path) -> list[Entry]:
    out = []
    lines = index_lines(root)
    for p in sorted(root.rglob("*.md")):
        parts = p.relative_to(root).parts
        if p.name.lower() in SKIP_FILES or any(x.startswith(".") or x in SKIP_DIRS for x in parts[:-1]):
            continue
        e = parse(p, root)
        e.extra["index_line"] = lines.get(e.name, "")
        out.append(e)
    return out


def terms(query: str) -> list[str]:
    return [t for t in WORD_RE.findall(fold(query)) if len(t) > 1 and t not in STOP]


# Russian inflection endings, longest first. Cutting one off and searching by prefix finds the
# other forms of the word ("ключом" -> "ключ*" finds "ключ", "ключа"). Cutting by length did
# not: "ключом" became "ключо", which matches nothing.
RU_ENDINGS = sorted("""
иями ями ами ого его ому ему ыми ими ых их ой ей ий ый ая яя ое ее ую юю ом ем ах ях ов ев ью
ия ие ии ся сь ть ешь ет ут ют ит ат ят ы и а я о е у ю ь й
""".split(), key=len, reverse=True)


def stem(term: str) -> str:
    """A light stem for Russian: strip one inflection ending, keep at least three letters.
    Latin words go to Porter untouched."""
    if CYRILLIC_RE.search(term):
        for end in RU_ENDINGS:
            if term.endswith(end) and len(term) - len(end) >= 3:
                return term[: -len(end)]
    return term


def match_expr(query: str, trigram: bool) -> str:
    parts = []
    for t in terms(query):
        s = stem(t).replace('"', "")
        if trigram:
            if len(s) >= 3:
                parts.append(f'"{s}"')
        else:
            parts.append(f'"{s}"*' if s != t else f'"{s}"')
    return " OR ".join(dict.fromkeys(parts))


def build(entries: list[Entry]) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    for table, tok in (("w", "porter unicode61 remove_diacritics 2"), ("t", "trigram")):
        db.execute(f"CREATE VIRTUAL TABLE {table} USING fts5(title, description, body, tokenize='{tok}')")
        db.executemany(f"INSERT INTO {table}(rowid, title, description, body) VALUES (?, ?, ?, ?)",
                       [(i, fold(e.name.replace("-", " ").replace("_", " ") + " " + e.title),
                         fold(e.description + " " + e.extra.get("index_line", "")), fold(e.body))
                        for i, e in enumerate(entries)])
    return db


def ranked(db: sqlite3.Connection, table: str, expr: str, depth: int = 50) -> list[int]:
    if not expr:
        return []
    try:  # title weighs most, then the description, then the body
        rows = db.execute(f"SELECT rowid FROM {table} WHERE {table} MATCH ? "
                          f"ORDER BY bm25({table}, 5.0, 3.0, 1.0) LIMIT ?", (expr, depth)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def search(entries: list[Entry], queries: list[str], mode: str = "words",
           db: sqlite3.Connection | None = None) -> list[tuple[int, float]]:
    """Rowids with fused scores, best first. mode: words, trigram or both."""
    db = db or build(entries)
    tables = {"words": ["w"], "trigram": ["t"], "both": ["w", "t"]}[mode]
    best: dict[int, float] = {}
    total: dict[int, float] = {}
    for q in queries:
        # Within one wording the tables are independent evidence: their reciprocal ranks add up.
        one: dict[int, float] = {}
        for table in tables:
            for rank, rowid in enumerate(ranked(db, table, match_expr(q, table == "t"))):
                one[rowid] = one.get(rowid, 0.0) + 1.0 / (RRF_K + rank + 1)
        # Wordings are alternatives, often in two languages, and an entry is usually written in
        # one: an entry the English wording ranks first is invisible to the Russian one. Summing
        # across wordings let entries sitting third to fifth in both lists overtake it (26.09.2026,
        # 2 of 4 misses). So an entry keeps its best wording; the sum only breaks ties.
        for rowid, s in one.items():
            best[rowid] = max(best.get(rowid, 0.0), s)
            total[rowid] = total.get(rowid, 0.0) + s
    return sorted(best.items(), key=lambda kv: (-kv[1], -total[kv[0]]))


def anchor(entry: Entry, queries: list[str]) -> str:
    """The body line that holds most of the query's stems: where to look inside the file."""
    stems = {stem(t) for q in queries for t in terms(q)}
    best, best_n = "", 0
    for line in entry.body.splitlines():
        low = fold(line)
        n = sum(1 for s in stems if s in low)
        if n > best_n:
            best, best_n = line.strip(), n
    return best[:160]


def outline(entry: Entry) -> str:
    out = []
    for block in re.split(r"\n\s*\n", entry.body.strip()):
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        head = lines[0].strip()
        if head.startswith("#"):
            out.append(head)
            continue
        first = re.split(r"(?<=[.!?:])\s", head, maxsplit=1)[0]
        out.append(("  " + first[:140]) + (" ..." if len(first) > 140 or len(lines) > 1 or first != head else ""))
    return "\n".join(out)


def find_entry(entries: list[Entry], name: str) -> Entry | None:
    key = name.removesuffix(".md").replace("\\", "/")
    for e in entries:
        if e.name == key or e.path.stem == key or e.title == key:
            return e
    return None


# -- evaluation -------------------------------------------------------------------------------

def read_cases(path: Path) -> list[tuple[list[str], str]]:
    """TSV: query <TAB> regex over the entry name. ` | ` inside the query separates several
    queries sent together (the English wording and the user's own words). # starts a comment."""
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "\t" not in line:
            continue
        query, expect = line.split("\t", 1)
        cases.append(([q.strip() for q in query.split(" | ") if q.strip()], expect.strip()))
    return cases


def evaluate(root: Path, cases: list[tuple[list[str], str]], mode: str = "words", ks=(3, 5)) -> dict:
    """Hits at k. A case whose expected entry does not exist is not a miss but a hole in the
    reference: it is listed apart and left out of the denominator."""
    entries = load(root)
    db = build(entries)
    names = [e.name for e in entries]
    hits = {k: 0 for k in ks}
    misses, broken = [], []
    for queries, expect in cases:
        rx = re.compile(expect, re.I)
        if not any(rx.search(n) for n in names):
            broken.append(f"{queries[0][:50]}  ->  no entry matches /{expect}/")
            continue
        got = [names[i] for i, _ in search(entries, queries, mode, db)]
        pos = next((i for i, n in enumerate(got) if rx.search(n)), None)
        for k in ks:
            hits[k] += pos is not None and pos < k
        if pos is None or pos >= max(ks):
            misses.append(f"{queries[0][:50]}  ->  wanted /{expect}/, top: {', '.join(got[:3]) or 'nothing'}")
    return {"cases": len(cases) - len(broken), "hits": hits, "misses": misses, "broken": broken}


def default_cases(root: Path) -> Path:
    return root / "eval" / "recall-cases.tsv"


# -- command line -----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Search memory entries and read them by level.")
    ap.add_argument("--memory", help="memory folder (default: plugin option, or the folder above)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recall", help="one line per hit, nothing pasted")
    r.add_argument("queries", nargs="+", help="one or more wordings of the same question")
    r.add_argument("--limit", type=int, default=8)
    r.add_argument("--mode", choices=["words", "trigram", "both"], default="words")
    r.add_argument("--json", action="store_true")
    d = sub.add_parser("read", help="open one entry at a chosen depth")
    d.add_argument("name", help="entry name, file stem or path relative to the memory folder")
    d.add_argument("--level", choices=["abstract", "outline", "full"], default="outline")
    v = sub.add_parser("eval", help="hits at 3 and 5 on a reference set")
    v.add_argument("--cases", type=Path, help="TSV of cases (default: <memory>/eval/recall-cases.tsv)")
    v.add_argument("--mode", choices=["words", "trigram", "both"], default="words")
    args = ap.parse_args(argv)

    root = memory_folder(args.memory)
    if root is None or not root.is_dir():
        print("memory folder not found: pass --memory or configure the plugin", file=sys.stderr)
        return 2
    entries = load(root)

    if args.cmd == "recall":
        hits = search(entries, args.queries, args.mode)[: args.limit]
        rows = [{"name": entries[i].name, "type": entries[i].type, "path": str(entries[i].path),
                 "description": entries[i].description, "anchor": anchor(entries[i], args.queries),
                 "score": round(s, 4)} for i, s in hits]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        else:
            for n, row in enumerate(rows, 1):
                print(f"{n}. {row['name']}" + (f"  [{row['type']}]" if row["type"] else ""))
                print(f"   {row['description'][:200]}")
                if row["anchor"]:
                    print(f"   > {row['anchor']}")
            if not rows:
                print("nothing found; try other words, the English wording, or grep the folder")
        return 0 if rows else 1

    if args.cmd == "read":
        e = find_entry(entries, args.name)
        if e is None:
            print(f"no entry named {args.name!r}", file=sys.stderr)
            return 1
        if args.level == "full":
            print(e.path.read_text(encoding="utf-8", errors="replace"))
            return 0
        print(f"{e.name}  ({e.path})")
        print(f"type: {e.type or '-'}   source: {e.source or '-'}")
        print(f"description: {e.description}")
        if args.level == "outline":
            print()
            print(outline(e))
        return 0

    cases_path = args.cases or default_cases(root)
    if not cases_path.is_file():
        print(f"no reference cases at {cases_path}", file=sys.stderr)
        return 2
    res = evaluate(root, read_cases(cases_path), args.mode)
    n = res["cases"]
    print(f"recall ({args.mode}): hit@3 {res['hits'][3]}/{n}, hit@5 {res['hits'][5]}/{n}")
    for m in res["misses"]:
        print(f"   miss: {m}")
    for b in res["broken"]:
        print(f"   not measurable: {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
