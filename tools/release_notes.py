"""Release bookkeeping: the version in plugin.json, its CHANGELOG section, the git tag.

    python tools/release_notes.py --check                    plugin.json version has a changelog section
    python tools/release_notes.py --tag v0.0.1 --out notes.md tag matches the version; write its notes

One place decides the version (plugin.json: Claude Code keeps users on it until it changes);
the changelog and the tag are checked against it, so the three cannot drift apart silently.
Exit 0 ok, 1 mismatch.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def section(changelog: str, version: str) -> str | None:
    m = re.search(rf"^## \[?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    return m.group(1).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tag")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    if not SEMVER.match(version):
        print(f"plugin.json version {version!r} is not semver")
        return 1
    notes = section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    if not notes:
        print(f"CHANGELOG.md has no section '## {version}'")
        return 1
    if a.tag is not None and a.tag != f"v{version}":
        print(f"tag {a.tag} does not match plugin.json version {version} (expected v{version})")
        return 1
    if a.out:
        a.out.write_text(notes + "\n", encoding="utf-8")
    print(f"ok: version {version}, {len(notes.splitlines())} changelog line(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
