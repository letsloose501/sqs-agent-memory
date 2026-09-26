"""Extracts the first <svg>...</svg> (nested svg icons included) from an HTML file and writes
it to its own file. Used after a headless render of a DSL infographic (AntV Infographic) with
`chrome --headless --dump-dom`: the dump holds the whole document, and only the render inside
#container is needed.

Example:
    python extract_svg.py dump.html diagram.svg
"""

import re
import sys
from pathlib import Path


def extract_svg(html: str) -> str:
    start = html.index("<svg")
    tag_re = re.compile(r"</?svg\b")
    depth = 0
    end = None
    for m in tag_re.finditer(html, start):
        if html[m.start() : m.start() + 4] == "<svg":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                end = html.index(">", m.end()) + 1
                break
    if end is None:
        raise ValueError("no closing </svg>: the dump is incomplete or the render did not finish")
    return html[start:end]


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: extract_svg.py <dump.html> <out.svg>", file=sys.stderr)
        raise SystemExit(2)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    svg = extract_svg(src.read_text(encoding="utf-8"))
    dst.write_text(svg, encoding="utf-8")
    print(f"{dst} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
