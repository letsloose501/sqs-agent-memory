---
name: graphics
description: >-
  Shared machinery for diagrams, infographics and charts, for the other skills (notes) and
  directly. Use when a STRUCTURAL picture from a ready template is needed - a list, a
  comparison, SWOT, a funnel, a roadmap, a hierarchy - or a chart from real data with considered
  typography; or when another skill reaches the step "draw a diagram / chart" and is choosing
  the tool.
---

# graphics: diagrams and charts

One tool for two different jobs: **structural infographics from a template** (list, steps,
comparison, SWOT, funnel, hierarchy) and **charts from real data** (comparison, series, before/
after). The first is a vendored library (AntV Infographic), fully offline. The second is our own
generators (`chart_paired.py`, `chart_bars.py`). Everything lives in this skill; nothing is
fetched from other repositories at run time.

This skill **does not decide** where the finished picture goes or in what format: the calling
skill knows that (`notes` embeds `![[...].svg]` in Obsidian). `graphics` is responsible only for
producing the picture and making sure it does not lie.

Scripts: `${CLAUDE_PLUGIN_ROOT}/skills/graphics/scripts` (written `<scripts>` below and in the references):
`scripts/chrome_selfcheck.py`, `scripts/extract_svg.py`, `scripts/chart_paired.py`, `scripts/chart_bars.py`.

## Choosing the tool

| Need | How | Reference |
|---|---|---|
| List / comparison / SWOT / funnel / roadmap / hierarchy: **structure**, not data | AntV Infographic (vendored), DSL to SVG in headless Chrome | `references/antv-infographic.md` |
| Before/after, paired samples, real units per record | `scripts/chart_paired.py` (no Chrome) | `references/chart-generators.md` |
| Comparing categories, dashboard pace, ranking, KPIs | `scripts/chart_bars.py` (no Chrome) | `references/chart-generators.md` |
| Color, curves, continuous geometry (no template) | a hand-made generator (Python + SVG) | `${CLAUDE_PLUGIN_ROOT}/skills/notes/references/diagrams.md` |
| Flowchart / ER / UML / BPMN | Mermaid / PlantUML | outside this skill |

## Self-check: before the first picture of a session, not before each

Looking at the finished render (always required, below) catches a wrong **picture**. It does not
catch a silently broken **tool**: Chrome not found, `--dump-dom` taking the page before the render
finished, the vendored library not running (for example a BOM lost on a version update, see
`references/antv-infographic.md`). Such a tool returns a plausible but empty or cut result, and
looking at it shows nothing. So a known reference goes through the same pipeline before this
session's real renders are trusted:

```bash
uv run --no-project "<scripts>/chrome_selfcheck.py"
```

Chrome or Edge is found automatically (`--chrome <path>` to override). Exit 0: the pipeline is
healthy and works fully offline. Non-zero: do not trust this session's renders until the cause is
fixed (the message names what broke). `--skip-vendor` checks only the base pipeline (Chrome +
`--dump-dom` + `extract_svg.py`).

## Rendering and extracting the SVG

`scripts/extract_svg.py` pulls `<svg>...</svg>` (nested svg icons included) out of a
`chrome --headless --dump-dom` dump. Shared by AntV Infographic and any other DSL or HTML render
that puts its result in a container. The full recipe (HTML wrapper, Chrome flags,
`--virtual-time-budget`) is in `references/antv-infographic.md`.

## Checking the result: always required

No picture is embedded unchecked: render, **look at it** (Read a PNG snapshot, or read the SVG),
and only then hand it to the calling skill. A defect turns up almost every time. What to check and
in what order: `${CLAUDE_PLUGIN_ROOT}/skills/notes/references/diagrams.md`, section "Checking"; it applies to any
picture, whatever its source.

## References

- `references/antv-infographic.md`: the DSL, template categories, the render recipe
- `references/chart-generators.md`: `chart_paired.py` / `chart_bars.py`, the two reading paces
