# Limits and pitfalls

## What the snapshot cannot see

Same as jev: shadow DOM and iframe content do not make it into the table, nor does canvas. For
iframes use `iframe_target(url_substring)` and `js(expr, target_id=…)`. A custom dropdown
without a role shows up as `clickable` if it has `cursor:pointer`; if it does not, take a
screenshot and click with `click_at_xy`.

## Pitfalls

- `browser-harness --reload` on Windows fails with `PermissionError` on
  `runtime/bu-default.port`. Restarting Chrome with `bh.py --stop` and the next call work
  without it.
- A narrow window gets the mobile layout. `bh.py` starts Chrome at 1440x1000; if Chrome was
  opened by hand, check the width in the snapshot header.
- After `go()` to a new site the old `eN` refs are void: it is another page.

## Native dialogs

A native `alert`/`confirm`/`prompt`/`beforeunload` freezes the page's JS: every `js()` hangs
for 5 s and fails with a bare "Runtime.evaluate timed out", and a `confirm` inside `onclick`
blocks the click's `mouseReleased` itself ("Input.dispatchMouseEvent timed out"). Both were
reproduced on 26.09.2026. The harness daemon records the dialog from CDP events, so it can be
asked without JS (`page_info()` returns `{dialog: …}`); the helpers use that:

- `act` runs the click in a thread and polls for a dialog meanwhile (playwright-core does the
  same in `_raceAgainstModalStates`): `native confirm "Удалить запись?"; page frozen…`;
- `snap()` prints `NATIVE DIALOG` and returns empty `items` plus `native_dialog`;
- `nav` raises `DialogOpen` instead of leaving the page;
- `dialog()` dismisses, `dialog(accept=True)` accepts, `text=` answers a prompt.

`DIALOG OPEN` in the snapshot header is something else: a visible HTML modal
(`role=dialog`, `<dialog open>`), part of the page, closed by a click on its button.

A dialog left open by a crashed script stays open in the agent Chrome: the next script starts
with `NATIVE DIALOG`/`DialogOpen`, `dialog()` clears it.
