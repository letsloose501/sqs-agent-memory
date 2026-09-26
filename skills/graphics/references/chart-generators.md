# Charts from real data: our own generators

**Own code.** Python builds SVG strings; palette and layout follow the `notes` skill's
`references/diagrams.md`, "Style". No dependencies beyond the standard library, no Chrome.

## Two reading paces

- **Slow** (`chart_paired.py`): the reader goes record by record; the real units of each record
  are visible, not aggregated. For a printed figure where every observation matters.
- **Fast** (`chart_bars.py`): the reader must get it in seconds: who is higher, what changed. Big
  shapes, minimal detail, the ranking visible at once. For a dashboard, a handout, a summary slide.

The pace is chosen by **the data contract** (what actually has to be shown), not by which picture
looks nicer.

## `chart_paired.py`: before / after (paired samples)

Horizontal rows, one row = one record: a "before" dot, an "after" dot, a line between them, the
delta labelled. Sorted by the size of the change by default.

```bash
uv run --no-project "<scripts>/chart_paired.py" data.csv \
  --label id --before pre --after post \
  --title "Results of the training stage" --unit points --out chart.svg
```

Legend words are flags (`--before-label`, `--after-label`, `--unit-label`, English by default), so
the chart can be labelled in the notes' language. The chart only visualises numbers that were
already validated; it never produces new ones.

## `chart_bars.py`: comparing categories (fast reading)

Big bars, labelled values, sorted descending, the first (main) bar in the accent color.

```bash
uv run --no-project "<scripts>/chart_bars.py" data.csv \
  --label category --value value \
  --title "Where we grew" --unit "%" --out chart.svg
```

`--unit-label` sets the word before the unit.

## Checking: always required

Both scripts are deterministic, but **render and look at the result before embedding**: a
generator can be syntactically fine and still lie (wrong sorting, swapped axes, overlapping
labels). How: the `notes` skill's `references/diagrams.md`, "Checking".

## When neither fits

Analogue data (color, curves, continuous geometry) is not for these: the calling skill has its own
hand-made generator. Structural infographics without real numbers (a list, SWOT, a hierarchy) go
to `antv-infographic.md`.
