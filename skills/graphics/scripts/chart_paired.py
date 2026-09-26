"""A paired "before / after" chart (own code, an original implementation, not ported).

The reading pace (slow, record by record, real units) follows Lupi's design language in
lieflat-charts; the implementation is ours: SVG built from Python strings, palette and layout
from the notes skill's diagrams reference ("Style").

Each row = one record (a participant, a category): a "before" dot, an "after" dot, a line between
them. Sorted by delta by default, so the big changes show first. Legend words are flags, so the
chart can be labelled in any language.

Example:
    python chart_paired.py data.csv --before pre --after post \
        --title "Results of the training stage" --unit points --out chart.svg
"""

import argparse
import csv


LABELS = {"before": "before", "after": "after", "unit": "unit"}  # legend text, set from the CLI

PALETTE = {
    "bg": "#faf9f7",
    "ink": "#23211e",
    "muted": "#6b6660",
    "grid": "#c9c4bc",
    "before": "#8f9779",   # muted: was
    "after": "#3b6ea5",    # accent: now
    "good": "#4a7a4a",     # positive delta
    "bad": "#a5473b",      # negative delta
}

ROW_H = 34
MARGIN_L = 220
MARGIN_R = 90
MARGIN_TOP = 90
MARGIN_BOTTOM = 40


def esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def read_rows(path: str, label_col: str, before_col: str, after_col: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for i, r in enumerate(rows, start=2):
        try:
            before = float(r[before_col].replace(",", "."))
            after = float(r[after_col].replace(",", "."))
        except (KeyError, ValueError) as e:
            raise ValueError(f"row {i}: {e}")
        label = r.get(label_col, str(i - 1))
        out.append({"label": label, "before": before, "after": after, "delta": after - before})
    return out


def build_svg(rows: list[dict], title: str, unit: str, sort_by_delta: bool) -> str:
    if sort_by_delta:
        rows = sorted(rows, key=lambda r: r["delta"])
    vals = [r["before"] for r in rows] + [r["after"] for r in rows]
    vmin, vmax = min(vals), max(vals)
    span = vmax - vmin or 1.0
    plot_w = 560
    plot_h = ROW_H * len(rows)
    width = MARGIN_L + plot_w + MARGIN_R
    height = MARGIN_TOP + plot_h + MARGIN_BOTTOM

    def x(v: float) -> float:
        return MARGIN_L + (v - vmin) / span * plot_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Inter, \'Segoe UI\', Helvetica, Arial, sans-serif">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="14" fill="{PALETTE["bg"]}"/>',
        f'<text x="32" y="40" font-size="22" font-weight="700" fill="{PALETTE["ink"]}">{esc(title)}</text>',
        f'<text x="32" y="62" font-size="13" fill="{PALETTE["muted"]}">'
        f'● {esc(LABELS["before"])} · ● {esc(LABELS["after"])}'
        f'{" · " + esc(LABELS["unit"]) + ": " + esc(unit) if unit else ""}</text>',
    ]

    # axis (a vertical line left of the dots) with ticks by value
    n_ticks = 5
    for t in range(n_ticks + 1):
        v = vmin + span * t / n_ticks
        gx = x(v)
        parts.append(
            f'<line x1="{gx:.1f}" y1="{MARGIN_TOP - 8}" x2="{gx:.1f}" y2="{MARGIN_TOP + plot_h}" '
            f'stroke="{PALETTE["grid"]}" stroke-width="0.7"/>'
        )
        parts.append(
            f'<text x="{gx:.1f}" y="{MARGIN_TOP - 14}" font-size="10" fill="{PALETTE["muted"]}" '
            f'text-anchor="middle">{v:.3g}</text>'
        )

    for i, r in enumerate(rows):
        cy = MARGIN_TOP + i * ROW_H + ROW_H / 2
        bx, ax = x(r["before"]), x(r["after"])
        color = PALETTE["good"] if r["delta"] > 0 else (PALETTE["bad"] if r["delta"] < 0 else PALETTE["muted"])
        parts.append(
            f'<text x="{MARGIN_L - 16}" y="{cy + 4:.1f}" font-size="12" fill="{PALETTE["ink"]}" '
            f'text-anchor="end">{esc(r["label"])}</text>'
        )
        parts.append(f'<line x1="{bx:.1f}" y1="{cy:.1f}" x2="{ax:.1f}" y2="{cy:.1f}" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{bx:.1f}" cy="{cy:.1f}" r="4.5" fill="{PALETTE["before"]}"/>')
        parts.append(f'<circle cx="{ax:.1f}" cy="{cy:.1f}" r="4.5" fill="{PALETTE["after"]}"/>')
        sign = "+" if r["delta"] > 0 else ("" if r["delta"] == 0 else "\u2212")
        parts.append(
            f'<text x="{MARGIN_L + plot_w + 14}" y="{cy + 4:.1f}" font-size="12" fill="{color}">'
            f'{sign}{abs(r["delta"]):.3g}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_csv")
    ap.add_argument("--label", default="id", help="column with the row label (default 'id')")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--title", default="Before / after")
    ap.add_argument("--before-label", default="before", help="legend text for the first point")
    ap.add_argument("--after-label", default="after", help="legend text for the second point")
    ap.add_argument("--unit-label", default="unit", help="legend word before the unit")
    ap.add_argument("--unit", default="")
    ap.add_argument("--no-sort", action="store_true", help="do not sort by delta, keep the file order")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    LABELS.update(before=args.before_label, after=args.after_label, unit=args.unit_label)
    rows = read_rows(args.data_csv, args.label, args.before, args.after)
    svg = build_svg(rows, args.title, args.unit, sort_by_delta=not args.no_sort)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"{args.out} ({len(svg)} bytes, {len(rows)} rows)")


if __name__ == "__main__":
    main()
