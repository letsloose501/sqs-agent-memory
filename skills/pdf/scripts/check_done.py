#!/usr/bin/env python3
"""
Exit check for the `pdf` skill: step C really done, not just said.

Closes three recurring failures:
  1. The extracted markdown was "deleted" but the file is still there. In PowerShell brackets
     in a name are swallowed silently, and `Remove-Item` without -LiteralPath reports success
     having deleted nothing. The "<title> - scans" folder stays behind the same way.
  2. The PDF was processed but the registry has no row: next time it is processed again.
  3. A NOT PROOFREAD marker is left: a page was never read, a piece of the document is lost
     silently. Checked before the file is deleted, from what is left in the folder.

Usage:
    python check_done.py --vault <vault> --title "Exact title"
    python check_done.py --vault <vault>          # only check the folder is clean

Exit code: 0 clean, 1 something left open, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

REGISTRY = "Processed.md"
PERMANENT = {REGISTRY}
SCAN_MARKERS = ("NOT PROOFREAD",)


def nfc(text: str) -> str:
    """Names from macOS arrive in NFD and do not match NFC byte for byte."""
    return unicodedata.normalize("NFC", text)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Check step C of the pdf skill")
    ap.add_argument("--vault", type=Path, required=True, help="vault root")
    ap.add_argument("--title", help="exact title (as in the extracted markdown's frontmatter)")
    ap.add_argument("--dir", default="PDF", help="the PDF folder inside the vault (default PDF)")
    args = ap.parse_args()

    folder = args.vault.expanduser() / args.dir
    if not folder.is_dir():
        print(f"ERROR: no folder {folder}", file=sys.stderr)
        return 2

    problems: list[str] = []
    permanent = {nfc(n) for n in PERMANENT}
    files = [p for p in folder.iterdir() if p.is_file() and nfc(p.name) not in permanent]
    shots = [p for p in folder.iterdir() if p.is_dir() and p.name.endswith(" - scans")]

    unread = []
    for p in files:
        if p.suffix.lower() == ".md":
            body = p.read_text(encoding="utf-8", errors="replace")
            n = sum(body.count(m) for m in SCAN_MARKERS)
            if n:
                unread.append((p, n))
    if unread:
        problems.append("PAGES NOT PROOFREAD: they will be lost silently")
        for p, n in unread:
            problems.append(f"   {p.name}: {n} marker(s) left")
        problems.append(
            "   FIX: open the PNGs from the '<title> - scans' folder with Read, read the page and\n"
            "   replace the marker with its text. Only then step B and the deletion.")
    if files:
        problems.append(f"EXTRACTED TEXT NOT DELETED: {len(files)}")
        for p in files:
            problems.append(f"   {p.name}  ({p.stat().st_size // 1024} KB)")
    if shots:
        problems.append(f"SCAN FOLDERS NOT DELETED: {len(shots)}")
        for p in shots:
            problems.append(f"   {p.name}/")
    if files or shots:
        problems.append(
            "   FIX: in PowerShell delete strictly with -LiteralPath, or brackets in the name are\n"
            "   swallowed and nothing is deleted:\n"
            '     Remove-Item -LiteralPath "<full path>" -Recurse -Force\n'
            "   Then run this check again: 'deleted' without a check does not count.")

    registry = folder / REGISTRY
    if args.title:
        if not registry.is_file():
            problems.append(f"NO REGISTRY: {registry}")
            problems.append(f"   FIX: create {REGISTRY} with the header\n"
                            "     | date | title | PDF type | pages | what was extracted |")
        elif nfc(args.title) not in nfc(registry.read_text(encoding="utf-8", errors="replace")):
            problems.append(f'NO REGISTRY ROW: "{args.title}"')
            problems.append(
                f"   FIX: append to {REGISTRY} a row\n"
                "     | YYYY-MM-DD | title | PDF type | pages | what was extracted |\n"
                "   Take the title verbatim from the extracted markdown's frontmatter: the file\n"
                "   name and the title inside the PDF often differ.")
    else:
        print("(!) no --title: the registry row was not checked\n")

    if problems:
        print("STEP C NOT CLOSED\n")
        print("\n".join(problems))
        return 1
    print("OK: folder clean" + (", registry row present" if args.title else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
