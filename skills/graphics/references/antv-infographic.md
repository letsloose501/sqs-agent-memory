# AntV Infographic: template infographics

For **discrete structures** (lists, steps, comparing options, SWOT, funnel, roadmap, hierarchy or
mindmap) instead of a hand-made SVG generator: [AntV Infographic](https://github.com/antvis/Infographic)
(MIT). A DSL description is rendered to SVG by a ready library, with no shapes drawn by hand.

**Vendored locally**: `vendor/antv-infographic/infographic.min.js` in this skill (MIT,
`vendor/antv-infographic/LICENSE`). No internet and no unpkg/GitHub access is needed at run time;
the upstream repository is needed only to update the version.

The file starts with a UTF-8 BOM (`\xef\xbb\xbf`): **keep it when updating**. Without it Chrome on a
non-Latin locale may decode the file with the wrong encoding (the bundle contains Chinese text) and
hit a syntax error out of nowhere. To update:
`curl -sL -o infographic.min.js "https://unpkg.com/@antv/infographic@latest/dist/infographic.min.js"`,
put the BOM back (`b"\xef\xbb\xbf" + data`), check with `node --check`, run `chrome_selfcheck.py`.

**Not for analogue things** (color, curves, geometry, shape): the calling skill has its own
generator for those. Use this only when the content itself is a list, steps or a comparison and a
template exists for it.

## DSL

A short indented grammar: the first line `infographic <template>`, then `data` (title/desc plus one
main block for the template: `lists` / `sequences` / `compares` / `root` / `nodes` / `values`) and
optionally `theme.palette`. The full syntax and template list live in `infographic-creator/SKILL.md`
inside the [antvis/Infographic](https://github.com/antvis/Infographic) repository (someone else's
repository, open it with WebFetch when needed).

Template families:
- `list-*`: a list of items
- `sequence-*`: steps or stages; `sequence-funnel-*` a funnel; `sequence-roadmap-*` a roadmap
- `compare-binary-*`: two options; `compare-swot`: SWOT; `compare-quadrant-*`: quadrants
- `hierarchy-*`: a tree; `hierarchy-mindmap-*`: a mindmap
- `chart-*`: simple charts (line/bar/pie/wordcloud); for real data prefer `chart-generators.md`

## Rendering to SVG

Headless Chrome with `--dump-dom`, then `scripts/extract_svg.py`. The vendored file is copied next to
the HTML wrapper (a relative `<script src>`, no network). Write the wrapper with the Write tool, not
a shell heredoc:

`<temp>/render.html`:
```html
<div id="container"></div>
<script src="vendor/antv-infographic/infographic.min.js"></script>
<script>
  const ig = new AntVInfographic.Infographic({ container: '#container', width: 900, height: 600 });
  ig.render(`YOUR_DSL_HERE`);
</script>
```

```bash
mkdir -p "<temp>/vendor/antv-infographic"
cp "<scripts>/../vendor/antv-infographic/infographic.min.js" "<temp>/vendor/antv-infographic/"
chrome --headless --no-sandbox --disable-gpu --virtual-time-budget=4000 \
  --user-data-dir="<temp>/chrome-profile" --dump-dom "file:///<temp>/render.html" > "<temp>/dump.html"
uv run --no-project "<scripts>/extract_svg.py" "<temp>/dump.html" "<where the calling skill wants it>.svg"
```

`--virtual-time-budget` lets the library's script finish and insert the `<svg>` before the dump is
taken; without it `--dump-dom` may take the page before the render.

**On Windows under Git Bash, build the file URI with `cygpath -m`**, never from an MSYS path:
`file:///$TMP/render.html` with `$TMP` from `mktemp -d` gives Chrome an invalid URI, and it silently
returns a "file not found" page instead of the render. From Python, `Path(...).as_uri()` is always
right; `chrome_selfcheck.py` does that.

## Before a batch of real diagrams

Run the pipeline self-check (`SKILL.md`, "Self-check") once at the start of the session.

## After rendering

Where to save and how to embed is the calling skill's decision (for `notes`: `<Topic>/Diagrams/` and
`![[...]]`). "Render, then look at it" is required either way, before embedding.
