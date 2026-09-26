# Helpers

Everything is available in a script without an import: the harness loads
`workspace/agent_helpers.py`. Covered by `scripts/selftest.py` (59 checks; pagination runs on
`tests/list.html`, which reproduces the hh, habr, vc and funpay traps).

## Page

| Helper | What it does |
|---|---|
| `go(url, **snap)` | `nav()` then a snapshot; snapshot params pass through |
| `nav(url)` | navigate without a snapshot: waits for the new document and `settle()`, returns the URL |
| `snap(text=3000, all=False, limit=150, quiet=False)` | snapshot; `all` adds offscreen and covered controls; result has `captcha` and `native_dialog` (then `items` is empty: the page is frozen) |
| `find("text", role=None)` | controls by label or aria across the whole page; prints every match |
| `links(href_regex, min_text=15, limit=100)` | links with text from the whole page, longest text per URL; for title lists |
| `cards(item_url_regex, limit=60, max_lines=12)` | item cards of a result list: the block around each item link, as text lines; `key` is the path, or the full URL when one path carries more than 5 queries (funpay `/lots/offer?id=N`) |
| `paginate(collect, after=None, limit=200, pages=20, how="auto", key=None, pause=1.0, patience=2, wait=8.0)` | walk a list page by page, unique items; `collect` is a callable or an item regex (= `cards`); `.stopped` says why it ended |
| `pager(after=None)` | how the list goes on: `[{kind: next/more, how, label, href}]`, best first; `after` is the item regex that anchors the main list |
| `act(ref, force=False, wait=1.5)` | real mouse click at the center, checks nothing covers it; prints and returns what changed (navigation, dialog, target's `expanded`/`checked`/`value`, elements, text), `[]` = nothing in `wait` s; reports a native dialog the click opened |
| `dialog(accept=False, text=None)` | handle a native alert/confirm/prompt/beforeunload; default dismiss; `text` answers a prompt; `None` if none open |
| `fill(ref, text, enter=False, force=False)` | replace a field's content, Cyrillic, `contenteditable` |
| `pick(ref, "text")` | option of a native `<select>` by text or value, fires `change` |
| `settle(timeout=8)` | wait until the DOM stops changing and there is text |
| `page_text(limit, selector)` | all text of the page or an element, not only the viewport |

## Site data

| Helper | What it does |
|---|---|
| `sniff(lambda: action, pattern=None, noise=False)` | runs the action and captures the page's XHR/fetch: id, method, status, type, size, URL, POST body; ads, analytics and media dropped |
| `api_body(id)` | response body of a captured request straight from the browser, JSON parsed |
| `fetch_json(url, method="GET", body=None, headers=None, credentials="same-origin")` | request from the page with its origin (and cookies for same-origin); a dict body goes as JSON; status 400+ and network/CORS failures raise |
| `replay(call, url=None, body=None)` | resend a request caught by `sniff` with its own method, headers and body; change URL or body |
| `embedded_json()` | JSON baked into the page: JSON `<script>`/`<template>`, `window.ytInitialData`, `__INITIAL_STATE__` and the like, with sizes |
| `embedded("window.X" or "css")` | gets that JSON |
| `json_paths(obj, "word", keys_only=False)` | paths in a big JSON to keys (and strings) with the word; lists show their size |
| `http_get(url, headers=None)` | request without the browser, from the harness |

## CAPTCHA handoff

| Helper | What it does |
|---|---|
| `captcha()` | kinds of visible CAPTCHA, `[]` if none; detection only |
| `show()` | bring the agent Chrome to the front for the user |
| `wait_captcha_gone(timeout=600, poll=1)` | block until the user solved it, then `settle()`; run in the background |

## From the harness

| Helper | What it does |
|---|---|
| `js(expr)`, `cdp("Domain.method", …)` | raw access |
| `capture_screenshot(path, max_dim=1200)` | viewport screenshot |
| `wait_for_element(selector, timeout)` | wait for a specific element |
| `list_tabs()`, `new_tab(url)`, `switch_tab(t)` | tabs |
| `press_key("Escape")` | a key to the focused element (close a menu, submit) |
| `upload_file(selector, path)` | file into an `<input type=file>` |

More: `browser-harness skill` prints its own guide; mechanics like iframes, uploads and
drag-and-drop are in its
[interaction-skills](https://github.com/browser-use/browser-harness/tree/main/interaction-skills).
