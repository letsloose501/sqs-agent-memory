---
name: browser
compatibility: Needs browser-harness (Python package browser_harness), installed as a uv tool at the reviewed commit (references/setup.md), and Chrome or Edge.
description: >-
  Fast scripted work with websites: browser-harness (CDP) plus a page snapshot as a numbered
  table, so one call can open, fill, click, walk result pages and extract data, and the site's
  own data (internal API, embedded JSON) comes before DOM parsing. Use when something has to
  be done on a site or pulled from it: "go to this site", "find it on a job board / marketplace",
  "collect from this page / from several pages", "scrape it", "get it through the site's API",
  "fill in the form", "click around the site", "does the search / form work", "screenshot the
  site"; and
  when WebFetch returned an empty shell, a refusal, or the page is rendered by JS. Plain
  reading of a public page, docs or a documented API is WebFetch/curl, not this. Showing the user a
  page in the app pane or their own dev server: the built-in browser. Acting in their main
  Chrome with their logins: Claude in Chrome.
---

# browser

The agent writes a short Python script; the script does everything that needs no fresh look
at the page in **one** call and prints a snapshot. Speed comes from the number of calls, not
from fast clicks: each call costs about a second of overhead, a snapshot costs 0.01-0.13 s.

Engine: [browser-harness](https://github.com/browser-use/browser-harness) (MIT), the Python package
`browser_harness`, installed separately as a uv tool (references/setup.md). The snapshot
is ported from [jev-ultrafast](https://github.com/browser-use/jev-ultrafast) (`snapshot.js`,
MIT): one CDP call instead of the accessibility tree and screenshots; for them it cut browser
protocol calls from 1,092 to 101. Pagination follows the ideas of
[maxun](https://github.com/getmaxun/maxun) (AGPL-3.0: ideas only, the code is ours). Racing a
click against a native dialog follows playwright-core's `_raceAgainstModalStates`
([playwright-cli](https://github.com/microsoft/playwright-cli), Apache-2.0). Install,
telemetry, profile: [references/setup.md](references/setup.md).

## Script first, the browser is reconnaissance

The rule: use a script wherever one can work; the browser walks a site to find
how its data and actions go (internal API, headers, anti-bot), so that a script or skill can be
written from that. Before opening a site, look for an existing script: `sites.md` for the site,
memory, the project's own tools. Kuper shows why: the browser hit a ServicePipe CAPTCHA and
then a "turn off your VPN" page, while a small curl_cffi script returned prices through the same
VPN in seconds. A site that will be used again ends the run with its recipe (endpoints,
params, what blocks) in [references/api.md](references/api.md), or a script.

## Which browser

| Task | Tool |
|---|---|
| A site that already has a script | the script, not a browser |
| Read a public page, docs, a documented API | WebFetch / curl, no browser |
| Many steps, a form, N result pages, a JS-rendered site, a site's internal API | **this skill** |
| The user wants to watch; their own dev server | built-in browser (`preview_start`, `browser_batch`) |
| Needs the user's logins from their main Chrome | Claude in Chrome |
| Transcript of a YouTube video | the `video` skill (`transcript.py`); the browser only does search and metadata |

When curl or WebFetch got `403` "Just a moment..." (Cloudflare) or a refusal, the browser
usually gets through: studwork.ru gave curl `403` and opened in the browser.

This skill runs a **separate** Chrome (own profile, port 9222). The user's main browser is never
touched. They can log in inside the agent profile themselves when needed.

## Data: API before DOM

When you need data (a list, fields, many pages) rather than an action, go down this ladder
and stop at the first rung that delivers.

1. **Public API** (`api.hh.ru`, anything documented). May refuse: `api.hh.ru` gave our
   network `403`, then hung.
2. **The page's internal API.** `sniff(lambda: nav(url))`, on a feed also a scroll or a click,
   shows where the page itself goes. Read with `api_body(id)`; for another page or query use
   `replay(call, url=…, body=…)`, which resends the page's own headers: a bare `fetch_json` of
   the WB search URL got `403`, `replay` got page 2. habr, vc, dzen, YouTube, plati, playerok
   and WB returned structure (price, seller, score, cursor) in 1-3 s per page this way.
   Another domain's API (`api.digiseller.com` from plati): keep the default
   `credentials="same-origin"`; `"include"` failed CORS.
3. **JSON baked into the HTML.** `embedded_json()`: hh puts the whole result list into
   `template#HH-Lux-InitialState` (50 vacancies with every field), YouTube into `ytInitialData`.
   Find the path with `json_paths(obj, "word", keys_only=True)`.
4. **DOM:** `cards()`, `links()` and `js()` with selectors, below; many pages via `paginate()`.
   funpay and ggsel have neither API calls nor stable embedded state, so they live here.

Per-site recipes and what can break: [references/api.md](references/api.md).

## Running

Anything longer than a line is written with `Write` into the scratchpad and passed as a file:

```bash
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/browser/scripts/bh.py" path/to/script.py
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/browser/scripts/bh.py" -c 'snap()'
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/browser/scripts/bh.py" --status     # Chrome alive? telemetry off?
```

`bh.py` starts the agent Chrome and sets the environment. No heredoc: the script goes to the
harness stdin, and long heredocs in Bash break silently here.

## Loop

```python
s = go("https://site/search?q=...")   # navigate + wait + snapshot
fill("e16", "Python стажёр")           # eN refs from the last snapshot
act("e18")                             # click; waits if the URL changed
snap(text=0)                           # fresh look at the end of the same script
```

The snapshot prints a header (title, URL, scroll, how many offscreen and covered, dialog open,
CAPTCHA), then controls `eN role "label" = "value" → href`, then visible text. Refs live in the
page (`window.__bh`), so they survive the next call while the page stays the same.

## Rules learned from runs

**URL params before the form, but check the results arrived.** On hh.ru the search box and
"Найти" opened a login modal, while `/search/vacancy?text=…&experience=noExperience` gave
filtered results at once. habr is the opposite: `/ru/search/?q=…` opens the form with the query
but no results ("Нажмите на иконку поиска") and `links()` returned zero. Empty where you
expect results: read the page text before changing selectors.

**Result list from the DOM: `cards(item_url_regex)`.** From each item link it climbs to the
largest block holding no link to another item and returns that card's text lines (title,
price, seller, rating) without per-site selectors: Yandex Market, ggsel, WB, ozon and hh gave
8-40 cards in 2-6 s. `links()` is for plain title lists (articles, videos); on product cards
it picks the wrong text (Market's longest link was the price, ggsel's product link says only
"Купить"). Exact fields via `js()` with selectors, looped over pages in one script.

**Article text: compare container lengths** (`article`, `main`, `[itemprop=articleBody]`) and
take the fullest with `page_text`. Per site: [references/sites.md](references/sites.md).

**A slow site outlives the daemon's 5 s wait on `Page.navigate`** (imnotarobot.fun, hh once).
`nav()` prints "slower than 5 s, still waiting" and keeps waiting; bare `goto_url` raises.

**Many pages of a DOM list: `paginate(item_regex)`, not a hand loop.** It finds how the list
goes on (a `rel=next` link, the page number after the active one, "Дальше", a "Показать ещё"
button, otherwise infinite scroll), walks it and stops by itself: the control is gone, rounds
bring nothing new, "next" leads to a visited page, a CAPTCHA, `limit`. Read `.stopped` before
reporting: 40 items at "last page" and at "control covered" are different answers. Items are
deduped because pages repeat records (hh re-ranks: 3 pages gave 150 rows, 100 unique); report
the unique count. Controls count only next to the main list, the block with most item links:
habr has article links after its pager, vc a widget with its own "Показать ещё" before the feed.
The string form collects with `cards()`; for title lists pass `lambda: links(P)` and `after=P`
(on habr `cards` returns 7 scraps). Checked on hh, habr, ggsel, funpay, vc on 24.09.2026. This
is the DOM rung: a feed with an internal API (vc, WB) is still faster via `sniff` and a cursor.

**Navigate with `go()`/`nav()`, not `goto_url()`.** `nav()` waits until the document itself is
replaced, then `settle()`. With bare `goto_url` and a pause the YouTube snapshot was taken from
the old page and returned `None`. `settle()` does not wait for `complete` (hh results ready at
1.6 s, `complete` at 7 s because of ads) and does not accept a page without text (studwork sat
on a spinner with an unchanged DOM). Waiting for something specific (a panel, a list after a
click): `wait_for_element(selector)`, since `settle()` is happy with any text.

**A `chrome-error://…` URL means retry once.** dzen once tripped on an empty response from its
SSO; the second attempt went through.

**Screenshot when the snapshot contradicts expectations.** Enter did not navigate, or the header
says "DIALOG OPEN" out of nowhere: one `capture_screenshot(path, max_dim=1200)` and `Read`. On
hh that showed a narrow window had served the mobile layout with a sheet over a modal. In a loop
that goes to plan, no screenshots.

**`fill` returns what the field accepted.** It prints any mismatch: maxlength, a mask or a
character filter is the site's answer, not a broken input. `force=True` pushes the value through
the native setter past those limits, only when you know the field swallows honest input.

**The snapshot sees only the viewport; search the whole page with `find("text")`.** On YouTube
the description expander "...ещё" was below the fold and missing, while the viewport held another
"Ещё" (the actions menu), and a click on the first hit went wrong. `find()` prints every match
with "offscreen": choose by context. Labels are the visible text; `aria-label` goes in brackets
when it differs ("Отклонить все" on YouTube has aria "Запретить использование файлов cookie…").

**Read what `act` says changed, and check it is the change you wanted.** `act` watches the
page up to 1.5 s and prints the difference: navigation, a dialog opening or closing, the
target's `expanded`/`checked`/`value`, elements and text added or removed; `nothing changed`
means the click did nothing visible. A change is not yet the right change: on YouTube the first
"Ещё" is the actions menu, its click gave `+20 elements, text +13 chars` while the description
stayed shut; the real "...ещё" gave `+803 elements, text +880 chars` (26.09.2026). When one
thing matters, check it directly: an attribute (`is-expanded`, `aria-expanded`), a new element,
a new URL. A change later than 1.5 s (a slow XHR) shows as `nothing changed`: pass `wait=`.

**`NATIVE DIALOG` (alert/confirm/prompt) freezes the page** until `dialog()` (dismiss) or
`dialog(accept=True)`; `act`, `snap` and `nav` report it instead of hanging. Details and how it
differs from `DIALOG OPEN`: [references/limits.md](references/limits.md).

**`act` errors say what to do.** "covered by X" means close X (often a modal with `Close` in
the snapshot). `StaleRef` means take a fresh `snap()`. A nudge modal can just be closed: on hh
closing it continued the search.

**Print only what you need.** `go()` and `snap()` print themselves; the snapshot has a short
`repr`, so `print(go(...))` will not dump the page. Cut text with `text=0` or `text=800`, many
controls with `limit=`.

## CAPTCHA: detect and hand over, never solve

Solving a CAPTCHA (checkbox, image grid, distorted text, slider puzzle, digits) is off limits for
the agent, including on the user's direct request: it exists to stop automation. The skill's job is to
notice it and hand the window to the user.

1. The snapshot header shows `CAPTCHA: kind`; `captcha()` returns the kinds (reCAPTCHA, hCaptcha,
   Cloudflare Turnstile and challenge page, Yandex SmartCaptcha and its `showcaptcha` page,
   GeeTest slider). The invisible reCAPTCHA v3 badge does not count: it blocks nothing.
2. `show()` brings the agent Chrome to the front.
3. Tell the user in chat: which site, what they need to do, that the script continues by itself.
4. Start `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/browser/scripts/bh.py" -c "wait_captcha_gone(600)"` with `run_in_background`; when it returns
   `CAPTCHA gone`, continue from the same page.

A CAPTCHA on every request means the site is pushing back: slow down or switch to its API
instead of asking the user again and again. A JS anti-bot check that the page passes by itself is
not a CAPTCHA: WB runs one on every visit (`__wbaas/challenges/antibot`, `498` then `200`),
the real browser clears it with no input, nothing to hand over.

## Boundaries

- Login, password, SMS code: stop and ask the user. SSO in an already logged-in profile is fine.
- A cookie banner with only "Понятно": leave it, agreeing for the user is not ours to do and there
  is no refusal. A "Reject" option: press it (YouTube: "Отклонить все").
- The page bounced to `/login`: a login wall, stop and tell the user (studwork calendar).
- Submitting a form, applying, buying, messaging: only after the user's yes to that exact action.
  `dialog(accept=True)` on a `confirm` ("Удалить?", "Отправить?", "Покинуть страницу?") is the
  same action: dismiss is the default, accept needs the user's yes. A plain `alert` has only OK.
- The user's data (email, name, phone) never goes into headers or params of requests to sites, even
  when an API asks for "contact in User-Agent". An email once leaked to `api.hh.ru` exactly this way.
- Internal APIs: read only and do not hammer, one page at a time, a human-like pause.

## Helpers

Page: `go`, `nav`, `snap`, `find`, `links`, `cards`, `act`, `fill`, `pick`, `dialog`, `settle`, `page_text`.
Lists: `paginate`, `pager`.
Data: `sniff`, `api_body`, `replay`, `fetch_json`, `embedded_json`, `embedded`, `json_paths`, `http_get`.
CAPTCHA handoff: `captcha`, `show`, `wait_captcha_gone`.
Signatures: [references/helpers.md](references/helpers.md).

## When it does not work

What the snapshot cannot see (shadow DOM, iframes, canvas) and known harness pitfalls on
Windows: [references/limits.md](references/limits.md). Per site: [references/sites.md](references/sites.md).
