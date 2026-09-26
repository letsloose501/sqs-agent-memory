"""PreToolUse hook on Read: surfaces what memory already knows about the file being read.

Why. Knowledge changes behaviour only where it is read. A memory entry about a tool's pitfall
("this script's --check does not validate the key", "delete these files with -LiteralPath") is
loaded only as one index line; the entry itself is opened when someone remembers to open it,
which is exactly the moment it is not remembered. This hook brings it in at the moment of
action: when the file is read, the entries and journal lessons that name it arrive with it.

The idea comes from claude-mem's file-context handler (a PreToolUse hook on Read that injects
past observations about the file, deduplicated per session). Here the source is not a log of
observations but the memory repository itself: entries in its root, in `projects/`, and the
`mistakes/` journal.

Matching. A file is recognised by its name (`check_links.py`), and for generic names
(`SKILL.md`, `README.md`, `__init__.py`...) only by `parent/name` (`video/SKILL.md`), since the
bare name would match everything. Names are compared NFC-normalised and case-insensitively.

What it cannot see: an entry that describes the file without naming it, and a file renamed
since the entry was written.

Output: JSON with `hookSpecificOutput.additionalContext` (PreToolUse stdout otherwise goes only
to the debug log). Each (session, file) pair is served once. Always exit 0: never block a Read.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from _common import memory_dir, plugin_data, read_payload, utf8_stdio

GENERIC = {"skill.md", "readme.md", "claude.md", "memory.md", "agents.md", "index.md", "index.html",
           "index.js", "index.ts", "__init__.py", "main.py", "app.py", "config.json", "settings.json",
           "package.json", "pyproject.toml", "requirements.txt", ".gitignore", "notes.md", "todo.md"}
MAX_ENTRIES = 5
MAX_LINE = 240
SKIP_NAMES = {"memory.md", "readme.md", "scopes.md"}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def needles(path: Path) -> list[str]:
    name = nfc(path.name)
    parent = nfc(path.parent.name)
    if name in GENERIC or len(path.stem) < 4:
        return [f"{parent}/{name}", f"{parent}\\{name}"] if parent else []
    return [name]


def entry_files(mem: Path) -> list[Path]:
    out = [p for p in mem.glob("*.md") if p.name.lower() not in SKIP_NAMES]
    out += [p for p in (mem / "projects").rglob("*.md") if p.name.lower() not in SKIP_NAMES]
    out += sorted((mem / "mistakes").glob("*.md"))
    return [p for p in out if p.is_file()]


def describe(p: Path, text: str) -> str:
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    if m:
        return m.group(1).strip().strip('"')
    m = re.search(r"^(PATTERN|ПАТТЕРН):\s*(.+)$", text, re.M)
    return ("lesson: " + m.group(2).strip()) if m else ""


def main() -> int:
    utf8_stdio()
    payload = read_payload()
    if payload.get("tool_name") != "Read":
        return 0
    raw = (payload.get("tool_input") or {}).get("file_path", "")
    mem = memory_dir()
    if not raw or mem is None or not mem.is_dir():
        return 0
    target = Path(raw)
    try:
        # Reading a memory entry itself adds nothing. Only entries: scripts and other tools kept
        # in the memory repository (hook scripts are, behind a junction) still get their notes.
        if target.suffix.lower() == ".md" and target.resolve().is_relative_to(mem.resolve()):
            return 0
    except (OSError, ValueError):
        pass
    keys = needles(target)
    if not keys:
        return 0

    # Serve each (session, file) once: a file re-read ten times should not repeat the notes.
    seen_file = plugin_data() / "file-context-seen.txt"
    stamp = f"{payload.get('session_id', '')}\t{nfc(str(target))}"
    try:
        seen = set(seen_file.read_text(encoding="utf-8").splitlines())
    except OSError:
        seen = set()
    if stamp in seen:
        return 0

    hits: list[str] = []
    for p in entry_files(mem):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        low = nfc(text)
        if not any(k in low for k in keys):
            continue
        line = next((ln.strip() for ln in text.splitlines() if any(k in nfc(ln) for k in keys)), "")
        rel = p.relative_to(mem).as_posix()
        desc = describe(p, text)
        hits.append(f"- {rel}: {desc[:MAX_LINE]}" + (f"\n  mentions it: {line[:MAX_LINE]}" if line else ""))
        if len(hits) >= MAX_ENTRIES:
            break
    if not hits:
        return 0

    try:
        with seen_file.open("a", encoding="utf-8") as fh:
            fh.write(stamp + "\n")
    except OSError:
        pass
    context = (f"Memory already has notes about {target.name} (from {mem.name}). Read the entry before "
               f"relying on it; it reflects what was true when written:\n" + "\n".join(hits))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "additionalContext": context}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - never block a Read
        raise SystemExit(0)
