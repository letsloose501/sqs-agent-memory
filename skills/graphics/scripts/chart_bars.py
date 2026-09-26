"""A quick bar chart: the "glance" reading pace (own code, an original implementation).

The idea (big shapes, minimal detail, the result visible in seconds) comes from the lieflat-charts
design language; the implementation is ours, from scratch. For dashboard handouts, summary slides,
KPIs; not for a printed figure read closely (that is chart_paired.py or a hand-made generator).

Example:
    python chart_bars.py data.csv --label category --value value \
        --title "Where we grew" --out chart.svg
"""

import argparse
import csv


UNIT_LABEL = ["unit"]  # set from the CLI

PALETTE = {
    "bg": "#faf9f7",
    "ink": "#23211e",
    "muted": "#6b6660",
    "bar": "#3b6ea5",
    "bar_top": "#a5473b",  # the top value: accent
}

ROW_H = 46
BAR_H = 26
MARGIN_L = 200
MARGIN_R = 80
MARGIN_TOP = 80
MARGIN_BOTTOM = 30


def esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def read_rows(path: str, label_col: str, value_col: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for i, r in enumerate(rows, start=2):
        try:
            value = float(r[value_col].replace(",", "."))
        except (KeyError, ValueError) as e:
            raise ValueError(f"row {i}: {e}")
        out.append({"label": r.get(label_col, str(i - 1)), "value": value})
    return out


def build_svg(rows: list[dict], title: str, unit: str, sort_desc: bool) -> str:
    if sort_desc:
        rows = sorted(rows, key=lambda r: r["value"], reverse=True)
    vmax = max((r["value"] for r in rows), default=1.0)
    vmax = vmax or 1.0
    plot_w = 480
    plot_h = ROW_H * len(rows)
    width = MARGIN_L + plot_w + MARGIN_R
    height = MARGIN_TOP + plot_h + MARGIN_BOTTOM

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Inter, \'Segoe UI\', Helvetica, Arial, sans-serif">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="14" fill="{PALETTE["bg"]}"/>',
        f'<text x="32" y="40" font-size="24" font-weight="700" fill="{PALETTE["ink"]}">{esc(title)}</text>',
    ]
    if unit:
        parts.append(f'<text x="32" y="62" font-size="13" fill="{PALETTE["muted"]}">{esc(UNIT_LABEL[0])}: {esc(unit)}</text>')

    for i, r in enumerate(rows):
        y = MARGIN_TOP + i * ROW_H + (ROW_H - BAR_H) / 2
        w = max(2.0, r["value"] / vmax * plot_w)
        color = PALETTE["bar_top"] if i == 0 and sort_desc else PALETTE["bar"]
        parts.append(
            f'<text x="{MARGIN_L - 16}" y="{y + BAR_H / 2 + 5:.1f}" font-size="15" fill="{PALETTE["ink"]}" '
            f'text-anchor="end">{esc(r["label"])}</text>'
        )
        parts.append(
            f'<rect x="{MARGIN_L}" y="{y:.1f}" width="{w:.1f}" height="{BAR_H}" rx="{BAR_H / 2:.0f}" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{MARGIN_L + w + 12:.1f}" y="{y + BAR_H / 2 + 6:.1f}" font-size="16" font-weight="800" '
            f'fill="{PALETTE["ink"]}">{r["value"]:.3g}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_csv")
    ap.add_argument("--label", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--unit", default="")
    ap.add_argument("--no-sort", action="store_true", help="do not sort descending, keep the file order")
    ap.add_argument("--unit-label", default="unit", help="word shown before the unit")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    UNIT_LABEL[0] = args.unit_label
    rows = read_rows(args.data_csv, args.label, args.value)
    svg = build_svg(rows, args.title or args.value, args.unit, sort_desc=not args.no_sort)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"{args.out} ({len(svg)} bytes, {len(rows)} rows)")


if __name__ == "__main__":
    main()
