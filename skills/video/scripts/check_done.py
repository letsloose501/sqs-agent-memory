#!/usr/bin/env python3
"""
Exit check for the `video` skill: step C really done, not just said.

Closes two recurring failures:
  1. The transcript was "deleted" but the file is still there. In PowerShell brackets in a
     name are swallowed silently, and `Remove-Item` without -LiteralPath reports success
     having deleted nothing.
  2. The video was processed but the registry has no row: next time it is processed again.

Usage:
    python check_done.py --vault <vault> --title "Exact video title"
    python check_done.py --vault <vault>          # only check the folder is clean

Exit code: 0 clean, 1 something left open, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

REGISTRY = "Processed.md"
QUEUE = "Queue.md"
PERMANENT = {REGISTRY, QUEUE}   # anything else in the folder is a leftover transcript


def nfc(text: str) -> str:
    """Names from macOS arrive in NFD and do not match NFC byte for byte."""
    return unicodedata.normalize("NFC", text)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Check step C of the video skill")
    ap.add_argument("--vault", type=Path, required=True, help="vault root")
    ap.add_argument("--title", help="exact video title (as in the transcript frontmatter)")
    ap.add_argument("--dir", default="Videos", help="the videos folder inside the vault (default Videos)")
    args = ap.parse_args()

    folder = args.vault.expanduser() / args.dir
    if not folder.is_dir():
        print(f"ERROR: no folder {folder}", file=sys.stderr)
        return 2

    problems: list[str] = []
    leftovers = [p for p in folder.iterdir()
                 if p.is_file() and nfc(p.name) not in {nfc(n) for n in PERMANENT}]
    if leftovers:
        problems.append(f"TRANSCRIPTS NOT DELETED: {len(leftovers)}")
        for p in leftovers:
            problems.append(f"   {p.name}  ({p.stat().st_size // 1024} KB)")
        problems.append(
            "   FIX: in PowerShell delete strictly with -LiteralPath, or brackets in the name are\n"
            "   swallowed and nothing is deleted:\n"
            '     Remove-Item -LiteralPath "<full path>" -Force\n'
            "   Then run this check again: 'deleted' without a check does not count.")

    registry = folder / REGISTRY
    if args.title:
        if not registry.is_file():
            problems.append(f"NO REGISTRY: {registry}")
        elif nfc(args.title) not in nfc(registry.read_text(encoding="utf-8", errors="replace")):
            problems.append(f'NO REGISTRY ROW: "{args.title}"')
            problems.append(
                f"   FIX: append to {REGISTRY} a row\n"
                "     | YYYY-MM-DD | title | channel | what was extracted (including the fact-check) |\n"
                "   Take the title verbatim from the transcript frontmatter: the registry is searched\n"
                "   by title; it stores no links or video IDs. A '|' in the title is written '\\|' in\n"
                "   the cell; then pass --title the part of the title before the '|'.")
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
