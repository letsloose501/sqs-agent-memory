#!/usr/bin/env python3
"""
Internal link check for an Obsidian vault.

Catches two mistakes that otherwise land in the vault silently:
  1. [[Note]]: no file with that name exists;
  2. [[Note#Section]]: the file exists, the heading does not.

Messages are written for an agent: what is broken, where, and what to do.

Usage:
    python check_links.py --vault <vault>                      # the whole vault
    python check_links.py --vault <vault> "path/to/Note.md"    # only these files
    python check_links.py --vault <vault> --section Programming  # only one section
    python check_links.py --vault <vault> --json               # machine-readable

`--section` narrows only WHAT is checked. Link targets are still collected from the whole
vault; otherwise a link from one section to a note in another would look broken.

Why a flag and not a filter: filtering the output outside (`| awk ...`) swallowed the exit
code, so empty output could not be told apart from "all clean". The exit code stays honest.

Exit code: 0 clean, 1 broken links found, 2 usage error (including a --section that matched
nothing: an empty selection is not "clean").
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

# Service folders: not scanned and not counted as targets.
SKIP_DIRS = {".obsidian", ".trash", ".git", "Excalidraw"}

# [[target]] / [[target|label]] / [[target\|label]] / [[target#section]] / ![[file]]
LINK_RE = re.compile(r"(!?)\[\[([^\[\]]+?)\]\]")

# Blocks inside which links are not real.
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

# MULTILINE is required: without it ^ and $ bind to the start and end of the whole text,
# no headings are collected, and the anchor check silently does nothing.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)

# Frontmatter: between the first pair of '---' at the very start of the file.
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", re.DOTALL)
ALIAS_KEY_RE = re.compile(r"^(alias(?:es)?)\s*:\s*(.*)$", re.IGNORECASE)


def norm(text: str) -> str:
    """Normalise a name for comparison: NFC + case fold + collapsed whitespace.

    NFC is required: names that came from macOS are stored in NFD (an accented letter as a
    base letter plus a combining mark), and without normalisation a name does not match itself.
    """
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split()).casefold()


def read_aliases(text: str) -> list[str]:
    """The note's aliases from its frontmatter: links may use them too.

    Without this every link through an alias ('Quick sort' -> file 'Quicksort.md') would be
    reported as broken, although it works in Obsidian.

    Understands three YAML forms: a block list, an inline list and a single string.
    """
    fm = FRONTMATTER_RE.match(text)
    if not fm:
        return []

    def clean(item: str) -> str:
        return item.strip().strip("'\"").strip()

    out: list[str] = []
    lines = fm.group(1).splitlines()
    for i, line in enumerate(lines):
        m = ALIAS_KEY_RE.match(line)
        if not m:
            continue
        value = m.group(2).strip()
        if value.startswith("["):                      # aliases: [A, "B"]
            out += [clean(x) for x in value.strip("[]").split(",")]
        elif value:                                     # alias: A
            out.append(clean(value))
        else:                                           # aliases:\n  - A
            for follow in lines[i + 1:]:
                if not follow.strip():
                    continue
                stripped = follow.lstrip()
                if not stripped.startswith("-") or not follow[:1].isspace():
                    break
                out.append(clean(stripped[1:]))
    return [a for a in out if a]


def strip_code(text: str) -> str:
    """Blank out code blocks and inline code, keeping line numbers."""
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else INLINE_CODE_RE.sub("``", line))
    return "\n".join(out)


def collect_targets(vault: Path) -> tuple[dict[str, list[Path]], dict[Path, set[str]]]:
    """Build the index: name without extension -> files, and file -> set of headings."""
    by_name: dict[str, list[Path]] = defaultdict(list)
    headings: dict[Path, set[str]] = {}

    for path in vault.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(vault).parts):
            continue

        by_name[norm(path.stem)].append(path)
        # The full name with extension, for embeds such as ![[diagram.svg]]
        by_name[norm(path.name)].append(path)

        if path.suffix.lower() == ".md":
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                headings[path] = set()
                continue
            for alias in read_aliases(raw):
                by_name[norm(alias)].append(path)
            body = strip_code(raw)
            found = {norm(m.group(2)) for m in HEADING_RE.finditer(body) if m.group(2).strip()}
            headings[path] = found

    return by_name, headings


def parse_link(raw: str) -> tuple[str, str | None]:
    """'Note#Section\\|label' -> ('Note', 'Section'). The label is dropped."""
    target = raw.split("|", 1)[0].replace("\\", "").strip()
    if "#" in target:
        name, _, anchor = target.partition("#")
        anchor = anchor.lstrip("^").strip()  # ^block references are not checked as headings
        return name.strip(), (anchor or None)
    return target, None


def check_file(
    path: Path,
    vault: Path,
    by_name: dict[str, list[Path]],
    headings: dict[Path, set[str]],
) -> list[dict]:
    try:
        body = strip_code(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return [{"file": str(path), "line": 0, "kind": "unreadable", "link": "", "detail": str(exc)}]

    problems: list[dict] = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        for embed, raw in LINK_RE.findall(line):
            name, anchor = parse_link(raw)
            if not name:
                continue  # [[#Section]]: a link inside the same note, no target needed

            matches = by_name.get(norm(name)) or by_name.get(norm(name + ".md")) or []
            # A link by path: 'Folder/Note', compare the tail of the path
            if not matches and "/" in name:
                tail = norm(Path(name).stem)
                matches = [
                    p for p in by_name.get(tail, [])
                    if norm(p.relative_to(vault).with_suffix("").as_posix()).endswith(norm(name))
                ]

            if not matches:
                problems.append({
                    "file": str(path.relative_to(vault)),
                    "line": lineno,
                    "kind": "missing_note",
                    "link": raw,
                    "detail": name,
                })
                continue

            if anchor:
                target = min(matches, key=lambda p: len(p.parts))
                known = headings.get(target, set())
                if known and norm(anchor) not in known:
                    problems.append({
                        "file": str(path.relative_to(vault)),
                        "line": lineno,
                        "kind": "missing_heading",
                        "link": raw,
                        "detail": anchor,
                        "target": str(target.relative_to(vault)),
                    })

    return problems


FIX_HINTS = {
    "missing_note": (
        "MISSING NOTES",
        "FIX: check the exact spelling with Glob and correct the name; or drop the square "
        "brackets and keep plain text; or create the note if it is really needed.",
    ),
    "missing_heading": (
        "HEADING MISSING IN THE TARGET FILE",
        "FIX: open the target file and copy the heading verbatim (case does not matter, "
        "everything else does); or link to the file without the `#` anchor.",
    ),
    "unreadable": ("FILE UNREADABLE", "FIX: check the encoding and permissions."),
}


def report(problems: list[dict], scanned: int) -> None:
    """A compact report: the "how to fix" hint once per kind of error, not per line."""
    if not problems:
        print(f"OK: no broken links ({scanned} files checked)")
        return

    files_total = len({p["file"] for p in problems})
    print(f"BROKEN LINKS FOUND: {len(problems)} in {files_total} files "
          f"({scanned} checked)")

    for kind in ("missing_note", "missing_heading", "unreadable"):
        group = [p for p in problems if p["kind"] == kind]
        if not group:
            continue

        title, hint = FIX_HINTS[kind]
        print(f"\n{'=' * 70}\n{title}: {len(group)}\n{hint}\n")

        by_file: dict[str, list[dict]] = defaultdict(list)
        for p in group:
            by_file[p["file"]].append(p)

        for file, items in sorted(by_file.items()):
            print(f"-- {file}")
            for p in sorted(items, key=lambda x: x["line"]):
                if kind == "missing_note":
                    print(f"   {p['line']:>5}: [[{p['link']}]]  -> no note \"{p['detail']}\"")
                elif kind == "missing_heading":
                    print(f"   {p['line']:>5}: [[{p['link']}]]  -> \"{p['target']}\" "
                          f"has no heading \"{p['detail']}\"")
                else:
                    print(f"   {p['line']:>5}: {p['detail']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Internal link check for an Obsidian vault")
    ap.add_argument("files", nargs="*", help="files to check (default: the whole vault)")
    ap.add_argument("--vault", type=Path, required=True, help="vault root")
    ap.add_argument(
        "--section",
        help="check only files whose path contains this string (e.g. "
             "'Programming'); link targets still come from the whole vault",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if args.files and args.section:
        print("ERROR: --section and a list of files make no sense together; pick one",
              file=sys.stderr)
        return 2

    vault: Path = args.vault.expanduser().resolve()
    if not vault.is_dir():
        print(f"ERROR: no vault at {vault}", file=sys.stderr)
        return 2

    by_name, headings = collect_targets(vault)

    if args.files:
        targets = []
        for raw in args.files:
            p = Path(raw)
            p = (p if p.is_absolute() else vault / p).resolve()
            if p.is_file():
                targets.append(p)
            else:
                print(f"ERROR: no file {p}", file=sys.stderr)
                return 2
    else:
        targets = [
            p for p in vault.rglob("*.md")
            if not any(part in SKIP_DIRS for part in p.relative_to(vault).parts)
        ]
        if args.section:
            # norm() is required here: folder names from macOS arrive in NFD and would not
            # match themselves on a plain comparison.
            needle = norm(args.section)
            targets = [p for p in targets if needle in norm(str(p.relative_to(vault)))]
            if not targets:
                print(f"ERROR: no file matched '{args.section}'. "
                      f"Check the section spelling: an empty selection is not 'clean'.",
                      file=sys.stderr)
                return 2

    problems: list[dict] = []
    for path in targets:
        problems.extend(check_file(path, vault, by_name, headings))

    if args.json:
        print(json.dumps(problems, ensure_ascii=False, indent=2))
    else:
        report(problems, len(targets))

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
