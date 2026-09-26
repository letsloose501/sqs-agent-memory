"""Fast layer over browser-harness: a page snapshot as a numbered table, actions by e1..eN refs,
and the site's own data (internal API, embedded JSON).

The harness loads this file from BH_AGENT_WORKSPACE; every public name is available in scripts
without an import. The snapshot technique comes from browser-use/jev-ultrafast: one CDP call
instead of the accessibility tree and screenshots, visible elements only.
"""
import base64
import json
import re
import threading
import time
from pathlib import Path

from browser_harness.helpers import cdp, click_at_xy, drain_events, goto_url, js, page_info, press_key

_SNAP_JS = (Path(__file__).resolve().parent / "snap.js").read_text(encoding="utf-8")


class Snap(dict):
    """A snapshot is a dict with a short repr, so a stray print(snap()) does not dump the page."""

    def __repr__(self):
        return f'<snap {self["url"]} · {len(self["items"])} controls>'


class StaleRef(RuntimeError):
    """A ref from an earlier snapshot no longer points to a live element: take a fresh snap()."""


class DialogOpen(RuntimeError):
    """A native alert/confirm/prompt is open: the page's JS is frozen until dialog() handles it."""


def _native_dialog():
    """The native dialog the harness daemon saw open ({type, message, url, ...}), or None.
    Asked without evaluating JS: with a dialog open every Runtime.evaluate hangs, and snap()
    used to fail after 5 s with a bare "Runtime.evaluate timed out" (26.09.2026)."""
    try:
        info = page_info()
    except RuntimeError:
        return None  # document is being swapped
    return info.get("dialog") if isinstance(info, dict) else None


def _dialog_line(d):
    return f'native {d.get("type", "dialog")} "{(d.get("message") or "")[:200]}"'


def _fmt(it):
    line = f'{it["ref"]} {it["role"]}'
    if it.get("label"):
        line += f' "{it["label"]}"'
    if "aria" in it:
        line += f' (aria: {it["aria"]})'
    if "value" in it:
        line += f' = "{it["value"]}"'
    if "options" in it:
        line += f' [{it["options"]} opts]'
    for k in ("checked", "selected", "expanded"):
        if k in it:
            line += f" {k}={it[k]}"
    if "href" in it:
        line += f' → {it["href"]}'
    if it.get("off"):
        line += " (offscreen)"
    return line


def snap(text=3000, all=False, limit=150, quiet=False):
    """Print and return a snapshot: header, controls with e1..eN refs, visible text.

    text   how many chars of visible text to print (0: none)
    all    include offscreen and covered controls (marked "offscreen")
    limit  cap on the number of controls
    """
    d = _native_dialog()
    if d:
        # Nothing on the page can be read until the dialog is handled: say so instead of hanging.
        s = Snap(title="", url=d.get("url", ""), items=[], text="", dialog=False, captcha=[], native_dialog=d)
        if not quiet:
            print(f"# NATIVE DIALOG: {_dialog_line(d)[7:]} · page frozen until dialog(accept=True/False)")
        return s
    opts = json.dumps({"text": text, "all": all, "limit": limit})
    s = js(f"({_SNAP_JS})({opts})")
    if s is None:
        print("# page has no body (about:blank or still loading)")
        return None
    s = Snap(s)
    s["native_dialog"] = None
    s["captcha"] = captcha()
    if quiet:
        return s
    sc = s["scroll"]
    # Anti-bot pages carry kilobytes of tokens in the query (kuper: ~4 KB); s["url"] keeps it whole.
    url = s["url"] if len(s["url"]) <= 200 else s["url"][:200] + f'… ({len(s["url"])} chars)'
    head = [f'# {s["title"]} | {url}',
            f'# scroll {sc["y"]}/{sc["h"]} (viewport {sc["vw"]}x{sc["vh"]})'
            + (f' · offscreen {s["offscreen"]}' if s["offscreen"] and not all else "")
            + (f' · covered {s["covered"]}' if s["covered"] and not all else "")
            + (" · DIALOG OPEN" if s["dialog"] else "")
            + (f' · CAPTCHA: {", ".join(s["captcha"])} (hand to the user, see SKILL.md)' if s["captcha"] else "")]
    print("\n".join(head + [_fmt(it) for it in s["items"]]))
    if text and s["text"]:
        print("---\n" + s["text"])
    return s


def find(text, role=None):
    """Find controls whose label (or aria) contains `text` across the WHOLE page, including
    offscreen and covered ones, and print them. A plain snapshot shows only the viewport: on
    YouTube the description expander "...ещё" sat below the fold and never showed up. The same
    label can belong to different buttons (there "Ещё" was also the actions menu), so look at
    every hit instead of taking the first. Returns refs; numbering is new, old refs are void."""
    s = snap(text=0, all=True, quiet=True, limit=1000)
    t = text.lower()
    hits = [it for it in s["items"]
            if (t in it["label"].lower() or t in it.get("aria", "").lower())
            and (role is None or it["role"] == role)]
    for it in hits:
        print(_fmt(it))
    if not hits:
        print(f"# find: {text!r} not found among {len(s['items'])} controls")
    return [it["ref"] for it in hits]


_RESOLVE_JS = """(ref => {
  const bh = window.__bh;
  if (!bh || !bh.refs) return {err: 'no snapshot on this page'};
  if (bh.url !== location.href) return {err: 'page changed since the snapshot'};
  const id = bh.refs[ref], e = id && bh.nodes.get(id);
  if (!e || !e.isConnected) return {err: 'element left the DOM'};
  let r = e.getBoundingClientRect();
  if (r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth) {
    e.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
    r = e.getBoundingClientRect();
  }
  if (r.width <= 0 || r.height <= 0) return {err: 'element became invisible'};
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const top = document.elementFromPoint(x, y);
  const lbl = e.labels && [...e.labels].some(l => l === top || l.contains(top));
  const ok = top && (top === e || e.contains(top) || top.contains(e) || lbl);
  const desc = n => n ? (n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') +
    (n.className && typeof n.className === 'string' ? '.' + n.className.trim().split(/\\s+/).slice(0, 2).join('.') : '') +
    ' "' + (n.innerText || '').trim().slice(0, 40) + '"') : 'nothing';
  return {x, y, ok, blocker: ok ? null : desc(top), tag: e.tagName, url: location.href};
})"""


def settle(timeout=8.0, quiet_ms=350, min_text=30):
    """Wait until the page stops changing: readyState is not 'loading', the DOM node count has
    not grown for quiet_ms, and the page has at least min_text chars of text.

    Does not wait for 'complete': hh.ru results were ready at 1.6 s while ads held 'complete'
    until 7 s. The text check is for spinners: studwork.ru sat with an unchanged DOM and an empty
    screen while fetching data and would otherwise count as ready (both measured 23.09.2026).
    Returns seconds waited."""
    t0 = time.time()
    last, stable_since = -1, None
    while time.time() - t0 < timeout:
        state, n, chars = js("[document.readyState, document.getElementsByTagName('*').length,"
                             " document.body ? document.body.innerText.trim().length : 0]")
        if state != "loading" and n == last and chars >= min_text:
            stable_since = stable_since or time.time()
            if (time.time() - stable_since) * 1000 >= quiet_ms:
                break
        else:
            stable_since = None
        last = n
        time.sleep(0.1)
    return round(time.time() - t0, 2)


def _resolve(ref):
    r = js(f"{_RESOLVE_JS}({json.dumps(ref)})")
    if r.get("err"):
        raise StaleRef(f"{ref}: {r['err']}, take a fresh snap()")
    return r


_SIG_JS = """(ref => {
  // Cheap page state for act(): what a click could have changed.
  const bh = window.__bh, id = bh && bh.refs && bh.refs[ref], e = id && bh.nodes.get(id);
  const vis = n => !n.checkVisibility || n.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  let tgt = null;
  if (e) tgt = !e.isConnected ? 'gone' : {
    expanded: e.getAttribute('aria-expanded'), pressed: e.getAttribute('aria-pressed'),
    selected: e.getAttribute('aria-selected'), checked: 'checked' in e ? e.checked : e.getAttribute('aria-checked'),
    open: 'open' in e ? e.open : null, value: typeof e.value === 'string' ? e.value.slice(0, 40) : null};
  return {url: location.href, els: document.getElementsByTagName('*').length,
          text: document.body ? document.body.innerText.length : 0,
          dlg: [...document.querySelectorAll('dialog[open],[role="dialog"],[aria-modal="true"]')].filter(vis).length,
          tgt};
})"""


def _changes(a, b):
    out = []
    if b["dlg"] != a["dlg"]:
        out.append("dialog opened" if b["dlg"] > a["dlg"] else "dialog closed")
    ta, tb = a["tgt"], b["tgt"]
    if tb == "gone" and ta != "gone":
        out.append("target left the DOM")
    elif isinstance(ta, dict) and isinstance(tb, dict):
        out += [f"{k} {ta[k]}→{tb[k]}" for k in ta if ta[k] != tb.get(k)]
    if b["els"] != a["els"]:
        out.append(f'{b["els"] - a["els"]:+d} elements')
    if b["text"] != a["text"]:
        out.append(f'text {b["text"] - a["text"]:+d} chars')
    return out


def _click(x, y):
    """click_at_xy raced against a native dialog; returns the dialog or None.
    A confirm() inside onclick blocks the mouseReleased CDP call until the dialog closes, and
    click_at_xy died after 5 s with "Input.dispatchMouseEvent timed out" (26.09.2026). The click
    runs in a thread; each harness call is its own IPC connection, so the dialog can be asked
    about meanwhile. Same idea as playwright-core's _raceAgainstModalStates."""
    err = []

    def run():
        try:
            click_at_xy(x, y)
        except Exception as e:  # noqa: BLE001
            err.append(e)

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(0.3)
    while th.is_alive():
        d = _native_dialog()
        if d:
            return d
        th.join(0.1)
    if err:
        d = _native_dialog()
        if d:
            return d
        raise err[0]
    return None


def act(ref, force=False, wait=1.5):
    """Click a snapshot ref with real CDP mouse events, checking that nothing covers it, and
    report what the click changed. Returns that report as a list ([] = nothing changed).

    Covered (modal, banner): raises and names the blocker; force=True clicks anyway.
    "Click sent" is not "click worked": on YouTube a click did not expand the description and
    nothing said so (23.09.2026). So act() watches the page up to `wait` seconds and prints the
    change: navigation, a dialog opening or closing, the target's aria-expanded/checked/value,
    elements and text added or removed; or "nothing changed". A native alert/confirm opened by
    the click is reported, not hung on: handle it with dialog().
    """
    r = _resolve(ref)
    if not r["ok"] and not force:
        raise RuntimeError(f"{ref}: covered by {r['blocker']}; close it or act(..., force=True)")
    sig = f"{_SIG_JS}({json.dumps(ref)})"
    before = js(sig)
    d = _click(r["x"], r["y"])
    t0 = time.time()
    after, changed_at = before, None
    while time.time() - t0 < wait + 5:
        if not d:
            time.sleep(0.1)
            d = _native_dialog()
        if d:
            print(f"# {ref}: click → {_dialog_line(d)}; page frozen until dialog(accept=True/False)")
            return [_dialog_line(d)]
        try:
            after = js(sig)
        except RuntimeError:
            continue  # document is being swapped by a navigation
        if after["url"] != r["url"]:
            settle()
            url = js("location.href")
            print(f"# {ref}: click → navigated to {url}")
            return [f"navigated to {url}"]
        if changed_at is None and _changes(before, after):
            changed_at = time.time()
        # Once something moved, give it 0.3 s to finish (a list rendering in two steps).
        if changed_at and time.time() - changed_at >= 0.3:
            break
        if not changed_at and time.time() - t0 >= wait:
            break
    got = _changes(before, after)
    print(f"# {ref}: click → " + (", ".join(got) if got else f"nothing changed in {wait:g} s"))
    return got


_FOCUS_JS = """(ref => {
  const bh = window.__bh, id = bh && bh.refs && bh.refs[ref], e = id && bh.nodes.get(id);
  if (!e || !e.isConnected) return false;
  e.scrollIntoView({block: 'center', behavior: 'instant'});
  e.focus();
  if (e.isContentEditable) {
    const s = getSelection(), r = document.createRange(); r.selectNodeContents(e); s.removeAllRanges(); s.addRange(r);
  } else if (e.select) { e.select(); }
  return true;
})"""

_VALUE_JS = """(ref => {
  const e = window.__bh.nodes.get(window.__bh.refs[ref]);
  return e.isContentEditable ? e.innerText : e.value;
})"""

_FORCE_VALUE_JS = """((ref, text) => {
  const e = window.__bh.nodes.get(window.__bh.refs[ref]);
  const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, text);
  e.dispatchEvent(new Event('input', {bubbles: true}));
  e.dispatchEvent(new Event('change', {bubbles: true}));
  return e.value;
})"""


def fill(ref, text, enter=False, force=False):
    """Replace a field's content with one Input.insertText (fast, Cyrillic works) and verify it.

    Returns what the field actually accepted and prints any mismatch: maxlength, an input mask
    or a character filter is the site's answer, not an input failure. force=True sets the value
    through the native setter with input/change events, bypassing those limits; use it only
    when you know the field swallows honest input. enter=True presses Enter afterwards.
    """
    ref_js = json.dumps(ref)
    if not js(f"{_FOCUS_JS}({ref_js})"):
        raise StaleRef(f"{ref}: element left the DOM, take a fresh snap()")
    cdp("Input.insertText", text=text)
    got = js(f"{_VALUE_JS}({ref_js})")
    if got != text and force:
        got = js(f"{_FORCE_VALUE_JS}({ref_js}, {json.dumps(text)})")
    if got != text:
        print(f"# {ref}: field accepted {got!r}, not {text!r}")
    if enter:
        press_key("Enter")
        time.sleep(0.4)
    return got


_PICK_JS = """((ref, want) => {
  const e = window.__bh.nodes.get(window.__bh.refs[ref]);
  if (!e || e.tagName !== 'SELECT') return {err: 'not a <select>'};
  const opts = [...e.options], w = want.trim().toLowerCase();
  const o = opts.find(o => o.label.trim().toLowerCase() === w || o.value === want)
         || opts.find(o => o.label.toLowerCase().includes(w));
  if (!o) return {err: 'no such option', have: opts.map(o => o.label.trim()).slice(0, 30)};
  e.value = o.value;
  e.dispatchEvent(new Event('input', {bubbles: true}));
  e.dispatchEvent(new Event('change', {bubbles: true}));
  return {label: o.label.trim()};
})"""


def pick(ref, option):
    """Choose an option of a native <select> by text or value. Custom dropdowns: act() on items."""
    r = js(f"{_PICK_JS}({json.dumps(ref)}, {json.dumps(option)})")
    if r.get("err"):
        raise RuntimeError(f"{ref}: {r['err']} {r.get('have', '')}")
    return r["label"]


def dialog(accept=False, text=None):
    """Close a native alert/confirm/prompt/beforeunload. Returns it ({type, message}) or None.

    Default is dismiss (Cancel). Accepting a confirm is pressing its button: "Удалить запись?",
    "Отправить?", "Покинуть страницу?" fall under the boundaries in SKILL.md, the user's yes first.
    text: the answer to a prompt()."""
    d = _native_dialog()
    if not d:
        print("# dialog: none open")
        return None
    params = {"accept": bool(accept)}
    if text is not None:
        params["promptText"] = text
    cdp("Page.handleJavaScriptDialog", **params)
    print(f"# dialog: {_dialog_line(d)} {'accepted' if accept else 'dismissed'}")
    return d


def go(url, **snap_kw):
    """Open a URL in the working tab, wait for it, then take a snapshot.
    Snapshot params (text, limit, all, quiet) are passed to snap() as is."""
    nav(url)
    return snap(**snap_kw)


def nav(url, timeout=15.0):
    """Navigate without a snapshot: wait until the document itself is replaced, then settle().

    A fixed pause after Page.navigate is not enough: on youtube.com settle() ran on the old
    page and the snapshot came back None (23.09.2026). A new document is detected by a changed
    performance.timeOrigin. A #hash-only change keeps the document. Returns the final URL."""
    d = _native_dialog()
    if d:
        raise DialogOpen(f"{_dialog_line(d)} is open on {d.get('url', '')[:80]}: handle it with dialog() first")
    before = js("[performance.timeOrigin, location.href.split('#')[0]]")
    try:
        goto_url(url)
    except Exception as e:  # noqa: BLE001
        # A slow server makes Page.navigate outlive the daemon's 5 s IPC wait, but the
        # navigation keeps going (imnotarobot.fun, 23.09.2026). Wait for it below instead.
        if "timed out" not in str(e):
            raise
        print(f"# nav: Page.navigate slower than 5 s, still waiting for {url[:80]}")
    if url.split("#")[0] != before[1]:
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if js("performance.timeOrigin") != before[0]:
                    break
            except RuntimeError:
                pass  # document is being swapped
            time.sleep(0.05)
    settle()
    return js("location.href")


_LINKS_JS = """((pat, minText, limit) => {
  // One card often has several links to one URL (thumbnail "4:05", title, author):
  // keep the longest text per URL, ordered by first appearance.
  const re = pat ? new RegExp(pat) : null, best = new Map();
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href.split('#')[0];
    if (re && !re.test(href)) continue;
    const text = (a.innerText || a.getAttribute('aria-label') || a.title || '').replace(/\\s+/g, ' ').trim();
    if (text.length < minText) continue;
    if (!a.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    const prev = best.get(href);
    if (!prev || text.length > prev.text.length) best.set(href, {text: text.slice(0, 200), href});
  }
  return [...best.values()].slice(0, limit);
})"""


def links(pattern=None, min_text=15, limit=100):
    """Links with meaningful text from the whole page (not just the viewport), one per URL.

    For feeds and result lists: article, video and post titles without per-site selectors.
    pattern: regex on href, e.g. r'/articles/\\d+' or r'/watch\\?v='.
    """
    return js(f"{_LINKS_JS}({json.dumps(pattern)}, {int(min_text)}, {int(limit)})")


_CARDS_JS = """((pat, limit, maxLines) => {
  // One item's links usually differ only by a tracking query (?src=img, ?src=title), so the key
  // is the path. But when one path carries many queries, the query IS the item: funpay lists
  // 1,878 offers as /lots/offer?id=N, and a path key glued them into one card (24.09.2026).
  const re = new RegExp(pat), path = h => h.split('#')[0].split('?')[0], queries = new Map();
  const matched = [...document.querySelectorAll('a[href]')].filter(a => re.test(a.href));
  for (const a of matched) {
    const p = path(a.href);
    if (!queries.has(p)) queries.set(p, new Set());
    queries.get(p).add(a.href.split('#')[0]);
  }
  const key = h => queries.get(path(h)).size > 5 ? h.split('#')[0] : path(h), groups = new Map();
  for (const a of matched) {
    const k = key(a.href);
    if (!groups.has(k)) groups.set(k, a);
  }
  const out = [];
  for (const [k, a] of groups) {
    // Climb while the parent holds no link to ANOTHER matching item: that parent is the card.
    let e = a;
    while (e.parentElement && e.parentElement !== document.body) {
      const p = e.parentElement;
      if ([...p.querySelectorAll('a[href]')].some(x => re.test(x.href) && key(x.href) !== k)) break;
      e = p;
    }
    if (!e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    // Lines from text nodes, not innerText: innerText glues sibling inline elements with no
    // separator ("Наушники Альфа1 151 ₽Купить"). Nodes of one parent are joined, so a price
    // split into "1 151" and "₽" stays one line.
    const parts = [], w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    let n, lastParent = null;
    while ((n = w.nextNode())) {
      const t = n.textContent.replace(/\\s+/g, ' ').trim(), par = n.parentElement;
      if (!t || !par || par.closest('script,style,noscript') || !par.checkVisibility()) continue;
      if (par === lastParent && parts.length) parts[parts.length - 1] += ' ' + t; else parts.push(t);
      lastParent = par;
    }
    const lines = [...new Set(parts)];
    out.push({href: a.href.split('#')[0], key: k, lines: lines.slice(0, maxLines)});
    if (out.length >= limit) break;
  }
  return out;
})"""


def cards(pattern, limit=60, max_lines=12):
    """Item cards of a result list: for every distinct item URL matching `pattern`, climb from the
    link to the largest ancestor that holds no link to ANOTHER item, and return its text lines.

    Use it when links() picks the wrong text: on Yandex Market the longest link text of a
    product was its price line, on ggsel the product link said only "Купить" (23.09.2026).
    Returns [{href, lines: [...]}]; pick title/price/seller from lines. URLs are compared
    without query, so the image link and the title link of one card count as one item."""
    return js(f"{_CARDS_JS}({json.dumps(pattern)}, {int(limit)}, {int(max_lines)})")


# --- Pagination: find how a list continues, walk it, stop when nothing new comes ---
# The idea (strategy types, stop rules, content signature against a "next" that goes nowhere)
# comes from getmaxun/maxun (AGPL-3.0): clientPaginationDetector.ts and handlePagination in
# maxun-core/src/interpret.ts. The code below is our own; patterns were set on real Russian
# sites on 24.09.2026.

# The main list: the deepest element holding >= 60% of the distinct item links. The last item
# link is no anchor: habr puts a "Читают сейчас" sidebar with article links AFTER its pager
# (62 of 65 item links precede "Туда"), vc puts a news widget with its own "Показать ещё"
# BEFORE the feed (24.09.2026). maxun anchors on the list container the same way.
_LIST_ROOT_JS = r"""function bhListRoot(after) {
  if (!after) return null;
  const re = new RegExp(after), its = [...document.querySelectorAll('a[href]')].filter(a => re.test(a.href));
  if (!its.length) return null;
  const keys = new Set(its.map(a => a.href.split('#')[0])), cnt = new Map();
  for (const a of its) for (let p = a.parentElement; p; p = p.parentElement) {
    if (!cnt.has(p)) cnt.set(p, new Set()); cnt.get(p).add(a.href.split('#')[0]);
  }
  const depth = e => { let d = 0; while ((e = e.parentElement)) d++; return d; };
  let root = null;
  for (const [el, s] of cnt) if (s.size >= 0.6 * keys.size && (!root || depth(el) > depth(root))) root = el;
  const inRoot = its.filter(a => root.contains(a));
  let scope = root;
  for (let i = 0; i < 4 && scope.parentElement && scope !== document.body; i++) scope = scope.parentElement;
  return {root, scope, first: inRoot[0], last: inRoot[inRoot.length - 1]};
}"""

_PAGER_JS = r"""((after) => {
  """ + _LIST_ROOT_JS + r"""
  const vis = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const off = e => e.disabled || e.getAttribute('aria-disabled') === 'true' || /\bdisabled\b/i.test(e.className || '');
  const text = e => (e.innerText || '').replace(/\s+/g, ' ').trim();
  const realHref = e => { const h = e.getAttribute('href'); return h && !/^(#|javascript:)/i.test(h) ? e.href : null; };
  // Narrow on purpose: [class*=pag] also matched "tm-page__main" wrappers on habr and vc.
  const PAGER = /paginat|pager|page-?nav|pagenav|pages-list|страниц/i;
  const inPager = e => !!e.closest('nav,[role=navigation]') && [...e.closest('nav,[role=navigation]').querySelectorAll('a,button')].filter(x => /^\d{1,4}$/.test(text(x))).length >= 2
    || [...function*(){ for (let p = e; p && p !== document.body; p = p.parentElement) yield p; }()].some(p =>
      PAGER.test((p.className && typeof p.className === 'string' ? p.className : '') + ' ' + (p.getAttribute('aria-label') || '') + ' ' + (p.getAttribute('data-qa') || '')));
  const NEXT = /^(дальше|далее|вперёд|вперед|следующая( страница)?|след\.?|next( page)?|[>›→»⟩]{1,2})$/i;
  const NEXT_ARIA = /следующ|^next( page)?$/i;
  // "Ещё" alone is not here: on YouTube it is the actions menu.
  const MORE = /^(показать|загрузить|смотреть)\s+(ещё|еще|больше)|^(ещё|еще)\s+\d+|^(load|show|view|see)\s+more|^more results$/i;
  const list = bhListRoot(after), itemRe = after ? new RegExp(after) : null;
  const ofList = e => !list || (list.scope.contains(e) && !!(list.first.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING));
  const CAROUSEL = '[class*=carousel i],[class*=slider i],[class*=swiper i],[class*=slick i]';
  const ok = e => vis(e) && !off(e) && ofList(e) && !(itemRe && e.href && itemRe.test(e.href))
    && !e.closest('header') && !e.closest(CAROUSEL);
  const found = [];
  const add = (kind, e, how, href) => found.push({kind, e, how, href, pager: inPager(e),
    label: text(e).slice(0, 40) || e.getAttribute('aria-label') || ''});
  const ctl = [...document.querySelectorAll('a,button,[role=button],[role=link]')].filter(ok);
  for (const e of ctl) {
    const t = text(e), aria = e.getAttribute('aria-label') || e.title || '';
    if (e.rel === 'next' || e.getAttribute('rel') === 'next') add('next', e, 'rel=next', realHref(e));
    else if (t.length <= 40 && (NEXT.test(t) || (!t && NEXT_ARIA.test(aria)) || (NEXT_ARIA.test(aria) && inPager(e)))) add('next', e, 'text', realHref(e));
    else if (t.length <= 50 && MORE.test(t)) add('more', e, 'text', realHref(e));
  }
  // Numbered pages: the link numbered active+1 inside a pager. Numbers outside a pager are
  // counters (comments, bookmarks: dozens of them on habr and vc), so a pager is required.
  const nums = ctl.filter(e => /^\d{1,4}$/.test(text(e)) && inPager(e));
  const active = [...document.querySelectorAll('[aria-current]:not([aria-current=false]),.active,.current,.selected,[class*="_active"],[class*="--active"],[class*="selected"]')]
    .filter(e => /^\d{1,4}$/.test(text(e)) && inPager(e)).map(e => +text(e));
  if (active.length) {
    const nx = nums.find(e => +text(e) === active[0] + 1);
    if (nx) add('next', nx, 'page ' + (active[0] + 1), realHref(nx));
  }
  const head = document.querySelector('link[rel=next][href]');
  // A "Далее" button with no href outside a pager is more likely a widget's arrow (habr has one
  // in an events block inside the article list) than the list's own pager: rank it last.
  const rank = f => f.how === 'rel=next' ? 0 : f.kind === 'next' && f.href ? 1 : f.kind === 'next' && f.pager ? 2
    : f.kind === 'more' ? 3 : 4;
  found.sort((a, b) => rank(a) - rank(b));
  document.querySelectorAll('[data-bh-pager]').forEach(e => e.removeAttribute('data-bh-pager'));
  const best = found[0];
  if (best) best.e.setAttribute('data-bh-pager', '1');
  const res = found.slice(0, 5).map(({kind, how, label, href}) => ({kind, how, label, href}));
  if (!best && head) return [{kind: 'next', how: 'link rel=next in head', label: '', href: head.href}];
  return res;
})"""

_CLICK_MARK_JS = """(() => {
  const e = document.querySelector('[data-bh-pager]');
  if (!e) return {err: 'pager control left the DOM'};
  e.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const top = document.elementFromPoint(x, y);
  const ok = top && (top === e || e.contains(top) || top.contains(e));
  return {x, y, ok, blocker: ok ? null : (top ? top.tagName.toLowerCase() + ' "' + (top.innerText || '').trim().slice(0, 40) + '"' : 'nothing')};
})()"""


# Infinite scroll: one jump to the list's last item, then a little further. Stepping by the
# viewport fell short: 8 steps covered 6,500 px while vc's list ended at 10,200 px, and the feed
# never loaded (24.09.2026). Without `after`, jump to the page bottom.
_SCROLL_JS = r"""(async (after) => {
  """ + _LIST_ROOT_JS + r"""
  const pause = () => new Promise(r => setTimeout(r, 300)), list = bhListRoot(after);
  if (list) list.last.scrollIntoView({block: 'end', behavior: 'instant'});
  else scrollTo(0, document.documentElement.scrollHeight);
  await pause();
  scrollBy(0, innerHeight * 0.3);
  await pause();
})"""


def pager(after=None, quiet=False):
    """How a result list continues: [{kind, how, label, href}], best first, [] if nothing.

    kind 'next' is a link or button to the next page (rel=next, "Дальше"/"Следующая"/"›", or the
    page number after the active one inside a pager); 'more' is a load-more button ("Показать
    ещё", "Загрузить ещё", "Ещё 20"). after: regex of item hrefs; only controls placed after the
    last item count, which keeps header menus and item links out. Infinite scroll has no control:
    paginate() tries scrolling when this returns []. The best hit is marked for paginate()."""
    found = js(f"{_PAGER_JS}({json.dumps(after)})")
    if not quiet:
        for f in found:
            print(f'# pager: {f["kind"]} via {f["how"]} "{f["label"]}"' + (f' → {f["href"]}' if f["href"] else ""))
        if not found:
            print("# pager: no next/more control (infinite scroll or the last page)")
    return found


def _item_key(it):
    # cards() already decided whether the query is tracking noise or the item id.
    if isinstance(it, dict) and it.get("key"):
        return it["key"]
    if isinstance(it, dict) and it.get("href"):
        return it["href"].split("#")[0].split("?")[0]
    return json.dumps(it, sort_keys=True, ensure_ascii=False)


class Items(list):
    """paginate() result: the unique items plus .stopped, why the walk ended."""
    stopped = ""


def paginate(collect, after=None, limit=200, pages=20, how="auto", key=None, pause=1.0, patience=2, wait=8.0):
    """Walk a result list page by page and return unique items; stops by itself.

    collect: a no-arg callable returning a list of items (lambda: cards(P), links(P), your js()),
             or a regex string, which means cards(regex) with after=regex.
    after:   regex of item hrefs for pager(): only controls after the last item count.
    how:     'auto' (next link → load-more button → scroll), or force 'next', 'more', 'scroll'.
    key:     item → dedupe key; default href without query and hash, else the whole item.
    Stops on: `limit` items, `pages` rounds, no control and scrolling brings nothing, `patience`
    rounds in a row without new items, "next" leading to an already visited URL, a CAPTCHA
    (hand it over, see SKILL.md), a covered control (close the overlay and rerun).
    A 'next' with a real href is opened with nav(), not clicked: same result, reliable wait.
    Prints one line per round and the stop reason; the reason is part of the result, since
    "stopped at 40" means different things for "last page" and "control covered"."""
    if isinstance(collect, str):
        after = after or collect
        pat = collect
        collect = lambda: cards(pat, limit=500)  # noqa: E731
    key = key or _item_key
    seen, out = set(), []

    rows = [0]

    def take():
        new = 0
        batch = collect() or []
        for it in batch:
            k = key(it)
            if k not in seen:
                seen.add(k)
                out.append(it)
                new += 1
        rows[0] = len(batch)
        return new

    def gathered(timeout):
        """Collect until new items stop arriving: two polls in a row with the same total."""
        t0, got, prev = time.time(), 0, -1
        while time.time() - t0 < timeout:
            settle(timeout=3)
            got += take()
            if got and len(out) == prev:
                break
            prev = len(out)
            time.sleep(0.5)
        return got

    got = take()
    visited = {js("location.href").split("#")[0]}
    print(f"# paginate: round 1: {got} items")
    dry, reason, rnd, mode = 0, f"{pages} rounds", 1, None
    while rnd < pages:
        if len(out) >= limit:
            reason = f"limit {limit}"
            break
        if captcha():
            reason = f"CAPTCHA {captcha()}: hand it to the user"
            break
        found = [] if how == "scroll" else [f for f in pager(after, quiet=True) if how == "auto" or f["kind"] == how]
        if not found and how in ("next", "more"):
            reason = f"no '{how}' control"
            break
        # A list that was paged by a control ends when the control is gone. Falling back to
        # scrolling there only cost two empty 8 s rounds on the last page of hh (24.09.2026).
        # One more look first: a load-more button may be disabled while its batch renders.
        if not found and mode:
            time.sleep(1.5)
            found = [f for f in pager(after, quiet=True) if how == "auto" or f["kind"] == how]
            if not found:
                reason = f"the '{mode}' control is gone: last page"
                break
        rnd += 1
        h0 = js("document.documentElement.scrollHeight")
        if found and found[0]["kind"] == "next" and found[0]["href"]:
            f = found[0]
            if f["href"].split("#")[0] in visited:
                reason = f'"next" leads to a visited page {f["href"][:80]}'
                break
            url = nav(f["href"]).split("#")[0]
            if url in visited:
                reason = f"landed on a visited page {url[:80]}"
                break
            visited.add(url)
            step, mode = f'next "{f["label"]}" → {url[:90]}', "next"
        elif found:
            f = found[0]
            r = js(_CLICK_MARK_JS)
            if r.get("err") or not r["ok"]:
                reason = f'{f["kind"]} "{f["label"]}" covered by {r.get("blocker") or r.get("err")}: close it and rerun'
                break
            click_at_xy(r["x"], r["y"])
            step, mode = f'{f["kind"]} "{f["label"]}" clicked', f["kind"]
        else:
            js(f"{_SCROLL_JS}({json.dumps(after)})")
            step = "scroll"
        got = gathered(wait)
        h1 = js("document.documentElement.scrollHeight")
        print(f"# paginate: round {rnd} {step}: +{got} new of {rows[0]} on the page, total {len(out)}")
        if not got:
            # A load-more button can render after the page settled: on ggsel "Показать ещё" was
            # missing right after nav() and present a second later (24.09.2026). Look again
            # before calling the list finished.
            if step == "scroll" and how == "auto" and pager(after, quiet=True):
                continue
            if step == "scroll" and h1 <= h0:
                reason = "no control, scrolling brings nothing: end of the list"
                break
            dry += 1
            if dry >= patience:
                reason = f"{patience} rounds in a row without new items"
                break
        else:
            dry = 0
        time.sleep(pause)
    print(f"# paginate: {len(out[:limit])} unique items in {rnd} rounds; stopped: {reason}")
    res = Items(out[:limit])
    res.stopped = reason
    return res


def page_text(limit=20000, selector=None):
    """All text of the page (or of one element), not only the viewport: for extraction."""
    sel = json.dumps(selector)
    return js(f"(()=>{{const e={sel}?document.querySelector({sel}):document.body;"
              f"return e?e.innerText.slice(0,{int(limit)}):null}})()")


# --- CAPTCHA: detect and hand to the user; never solve ---

_CAPTCHA_JS = """(() => {
  const vis = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) &&
    e.getBoundingClientRect().height > 30;
  const hits = new Set();
  for (const f of document.querySelectorAll('iframe')) {
    const s = f.src || '';
    if (!vis(f) || /size=invisible/.test(s)) continue;  // reCAPTCHA v3 badge blocks nothing
    if (/google\\.com\\/recaptcha|recaptcha\\.net/.test(s)) hits.add('recaptcha');
    else if (/hcaptcha\\.com/.test(s)) hits.add('hcaptcha');
    else if (/challenges\\.cloudflare\\.com/.test(s)) hits.add('cloudflare-turnstile');
    else if (/smartcaptcha|captcha-api\\.yandex/.test(s)) hits.add('yandex-smartcaptcha');
  }
  for (const [sel, kind] of [['.g-recaptcha', 'recaptcha'], ['.h-captcha', 'hcaptcha'],
      ['.cf-turnstile', 'cloudflare-turnstile'], ['.smart-captcha', 'yandex-smartcaptcha'],
      ['[class*="geetest"]', 'geetest-slider'], ['#challenge-form,#challenge-running', 'cloudflare-challenge']]) {
    const e = document.querySelector(sel); if (e && vis(e)) hits.add(kind);
  }
  if (/showcaptcha|checkcaptcha/.test(location.href)) hits.add('yandex-captcha-page');
  if (document.title === 'Just a moment...') hits.add('cloudflare-challenge');
  // ServicePipe "rotate the picture" page (kuper.ru, 26.09.2026: /xpvnsulc/, cookies spid/spsc).
  const sp = document.querySelector('#captcha_root');
  if (sp && vis(sp) && document.querySelector('script[src*="sp_rotated_captcha"]')) hits.add('servicepipe-rotate');
  // A vendor list always lags: kuper's ServicePipe was not on it and the snapshot said nothing.
  // Fallback: any visible block named captcha. The reCAPTCHA v3 badge is excluded, it blocks nothing.
  if (!hits.size) for (const e of document.querySelectorAll('[id*="captcha" i],[class*="captcha" i]')) {
    if (e.closest('.grecaptcha-badge') || !vis(e)) continue;
    hits.add('captcha, unknown vendor: ' + (e.id ? '#' + e.id : '.' + String(e.className).trim().split(/\\s+/)[0]));
    break;
  }
  return [...hits];
})()"""


def captcha():
    """Kinds of CAPTCHA visible on the page ([] if none). Detection only: solving CAPTCHAs is
    off limits for the agent, the user solves them (see show() and wait_captcha_gone())."""
    return js(_CAPTCHA_JS)


def show():
    """Bring the agent Chrome window and the working tab to the front, so the user can act in it.
    Only for a handoff (CAPTCHA, login, a choice that is the user's); normal work stays in the background."""
    cdp("Page.bringToFront")


def wait_captcha_gone(timeout=600.0, poll=1.0):
    """Block until no CAPTCHA is visible (the user solved it) or timeout. Then settle().
    Run it in the background and tell the user in chat what to do. Returns True if it is gone."""
    t0 = time.time()
    kinds = captcha()
    if not kinds:
        print("# no CAPTCHA on the page")
        return True
    print(f"# waiting for the user to solve: {', '.join(kinds)}")
    while time.time() - t0 < timeout:
        time.sleep(poll)
        try:
            if captcha():
                continue
            # One empty poll is not a solve: kuper's ServicePipe page reloads a fresh challenge
            # every few seconds, the poll hit the reload and reported "gone" while the check
            # still stood (26.09.2026). Settle, then it must stay absent for 3 more polls.
            settle()
            if any(time.sleep(max(poll, 0.5)) or captcha() for _ in range(3)):
                continue
            url = js("location.href")
            print(f"# CAPTCHA gone after {round(time.time() - t0)} s: {url[:200]}")
            return True
        except RuntimeError:
            pass  # page is navigating after the solve
    print(f"# CAPTCHA still there after {round(timeout)} s")
    return False


# --- Site data: capture, inspect, replay ---

_NOISE = re.compile(
    r"google-analytics|googletagmanager|doubleclick|googlesyndication|mc\.yandex|adfox|an\.yandex|"
    r"yandex\.ru/(ads|clck)|metrika|sentry|/collect\b|/beacon|/log_event|/logging|/stats?\b|"
    r"facebook\.com/tr|vk\.com/rtrg|top-fwz|/ping\b|/ptracking|/generate_204|/pagead/|"
    r"telemetry\.|/rtbcount/|adv?\.mail\.ru|adsrv\.|hybrid\.ai|/api/fl\b|/jnn/|^chrome-extension:|"
    # Map widgets: keys, styles, vector tiles. On kuper the address dialog's 2GIS map was all
    # 12 captured requests and hid the site's own calls (26.09.2026).
    r"\.2gis\.com/|maps\.yandex\.|api-maps\.yandex|maps\.googleapis\.com|\.mapbox\.com/")
# Response types that carry no data: player media, pixel images, scripts, styles, fonts.
# On dzen 30 of 49 requests were player video/audio and pixels (23.09.2026); kuper's map sent
# fonts as application/x-font-ttf, which ^font/ missed.
_NOISE_MIME = re.compile(r"^(image|video|audio|font)/|x-font|font-|javascript|css|dash\+xml|mpegurl")


def _post_preview(post):
    if not post:
        return ""
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in post[:400])
    if printable < 0.9 * min(len(post), 400):
        # YouTube sends the youtubei body gzipped: printing it is pointless.
        return f"  post: <binary body, {len(post)} bytes, likely gzip; see references/api.md>"
    return f"  post: {post[:120]!r}"


def sniff(action, seconds=10.0, idle_ms=800, pattern=None, noise=False):
    """Run action() and capture the XHR/fetch requests the page makes meanwhile.

    action: a no-arg callable, e.g. lambda: nav(url) or lambda: act("e5").
    Events are drained in parallel with the action: the daemon buffers only 500 events and a
    heavy page (YouTube, vc with ads) overflows that in seconds, so reading "after" loses them.
    Prints and returns: id, method, status, type, size, URL, POST body.
    Drops analytics, ads and media (noise=True keeps everything).
    Read a response with api_body(id), replay with other params via fetch_json(url, ...).
    """
    drain_events()
    reqs, errors = {}, []

    def run():
        try:
            action()
        except BaseException as e:  # noqa: BLE001: re-raised after collection
            errors.append(e)

    th = threading.Thread(target=run, daemon=True)
    t0 = last = time.time()
    th.start()
    while True:
        for e in drain_events():
            m, p = e.get("method", ""), e.get("params", {})
            rid = p.get("requestId")
            if m == "Network.requestWillBeSent" and p.get("type") in ("XHR", "Fetch"):
                r = p["request"]
                reqs[rid] = {"id": rid, "method": r["method"], "url": r["url"], "headers": r.get("headers", {}),
                             "post": r.get("postData"), "status": None, "mime": "", "kb": None}
                last = time.time()
            elif rid in reqs and m == "Network.responseReceived":
                reqs[rid]["status"] = p["response"]["status"]
                reqs[rid]["mime"] = p["response"].get("mimeType", "")
                last = time.time()
            elif rid in reqs and m == "Network.loadingFinished":
                reqs[rid]["kb"] = round(p.get("encodedDataLength", 0) / 1024, 1)
                last = time.time()
        if not th.is_alive() and (time.time() - last) * 1000 >= idle_ms:
            break
        if time.time() - t0 > seconds:
            break
        time.sleep(0.05)
    th.join(timeout=1)
    out, seen = [], set()
    for r in reqs.values():
        key = (r["method"], r["url"], r["post"])
        if key in seen or (pattern and not re.search(pattern, r["url"])):
            continue
        if not noise and (_NOISE.search(r["url"]) or _NOISE_MIME.search(r["mime"]) or r["status"] is None):
            continue
        seen.add(key)
        out.append(r)
    for r in out:
        print(f'{r["id"]}  {r["method"]:4} {r["status"]} {r["mime"][:24]:24} {r["kb"]}KB  '
              f'{r["url"][:140]}{_post_preview(r["post"])}')
    print(f"# sniff: {len(out)} of {len(reqs)} requests in {round(time.time() - t0, 1)} s")
    if errors:
        raise errors[0]
    return out


def api_body(request_id, raw=False):
    """Response body of a captured request (from sniff), straight from the browser, no refetch.
    Parses JSON; raw=True returns the string. Valid while the same page is open."""
    r = cdp("Network.getResponseBody", requestId=request_id)
    body = base64.b64decode(r["body"]).decode("utf-8", "replace") if r.get("base64Encoded") else r["body"]
    if raw:
        return body
    try:
        return json.loads(body)
    except ValueError:
        return body


_FETCH_JS = """(async (url, method, body, headers, credentials) => {
  try {
    const r = await fetch(url, {method, body, headers, credentials});
    return {status: r.status, ct: r.headers.get('content-type') || '', text: await r.text()};
  } catch (e) { return {status: 0, ct: '', text: String(e)}; }
})"""

# Headers the browser sets itself and refuses from scripts; replay() drops them.
_UNSAFE_HEADERS = re.compile(r"^(host|origin|referer|cookie|user-agent|content-length|connection|accept-encoding|"
                             r"sec-|:)", re.I)


def fetch_json(url, method="GET", body=None, headers=None, credentials="same-origin"):
    """Request made FROM the page: its origin, its cookies for same-origin URLs, so the site's
    internal API answers as it answers the page. A dict body is sent as JSON.
    credentials: 'same-origin' (default, like plain fetch), 'include' to send cookies cross-origin,
    'omit'. 'include' against another domain fails CORS unless that API allows credentials:
    api.digiseller.com from plati.market failed with 'include' and answered with 'same-origin'
    (23.09.2026).
    Returns parsed JSON (or text if not JSON); status >= 400 raises, a network/CORS failure too."""
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
        headers = {"Content-Type": "application/json", **(headers or {})}
    r = js(f"{_FETCH_JS}({json.dumps(url)}, {json.dumps(method)}, {json.dumps(body)}, "
           f"{json.dumps(headers or {})}, {json.dumps(credentials)})")
    if r["status"] == 0:
        raise RuntimeError(f"fetch_json network/CORS failure {url[:100]}: {r['text'][:150]}. "
                           f"Cross-origin: try credentials='omit', or http_get() outside the browser")
    if r["status"] >= 400:
        raise RuntimeError(f"fetch_json {r['status']} {url[:100]}: {r['text'][:200]}")
    try:
        return json.loads(r["text"])
    except ValueError:
        return r["text"]


def replay(call, url=None, body=None, credentials=None):
    """Repeat a request caught by sniff() with its own method, headers and body; change the URL
    (another page) or the body. Needed where the page adds anti-bot headers: a bare
    fetch_json of the WB search URL got 403 (23.09.2026). Browser-owned headers (cookie,
    origin, sec-*) are left to the browser."""
    headers = {k: v for k, v in (call.get("headers") or {}).items() if not _UNSAFE_HEADERS.match(k)}
    if credentials is None:
        credentials = "include" if any(k.lower() == "authorization" for k in headers) else "same-origin"
    return fetch_json(url or call["url"], method=call["method"],
                      body=body if body is not None else call.get("post"), headers=headers, credentials=credentials)


_EMBEDDED_JS = """(() => {
  const out = [];
  // Any inline <script> and any <template> whose content is entirely JSON.
  // hh.ru keeps the search state in <template id="HH-Lux-InitialState">, not in a script.
  for (const s of document.querySelectorAll('script:not([src]),template')) {
    const t = (s.tagName === 'TEMPLATE' ? s.innerHTML : s.textContent).trim();
    if (t.length < 1000 || !/^[\\[{]/.test(t)) continue;
    try { JSON.parse(t); } catch (e) { continue; }
    const sel = s.tagName.toLowerCase() + (s.id ? '#' + s.id : '') + (s.type ? '[type="' + s.type + '"]' : '');
    out.push({where: sel, kb: Math.round(t.length / 1024)});
  }
  for (const k of Object.keys(window)) {
    if (!/^(__|yt|initial|INITIAL|APOLLO|__APOLLO|__INITIAL|__PRELOADED|__NUXT|__REDUX)/.test(k) && !/(State|Data|STATE|DATA)$/.test(k)) continue;
    let v; try { v = window[k]; } catch (e) { continue; }
    if (!v || typeof v !== 'object') continue;
    let n = 0; try { n = JSON.stringify(v).length; } catch (e) { continue; }
    if (n > 2000) out.push({where: 'window.' + k, kb: Math.round(n / 1024)});
  }
  return out;
})()"""


def embedded_json():
    """Data baked into the page: JSON <script>/<template>, __NEXT_DATA__, window.ytInitialData,
    window.__INITIAL_STATE__ and the like. Prints where and how many KB.
    Get it with embedded("window.ytInitialData") or embedded("template#HH-Lux-InitialState")."""
    found = js(_EMBEDDED_JS)
    for f in found:
        print(f'{f["kb"]:>6} KB  {f["where"]}')
    if not found:
        print("# embedded_json: nothing above 2 KB")
    return found


def embedded(where):
    """Get embedded JSON by a string from embedded_json(): 'window.X' or a CSS selector."""
    if where.startswith("window."):
        return js(f"JSON.parse(JSON.stringify({where}))")
    return js(f"(()=>{{const s=document.querySelector({json.dumps(where)});"
              f"return JSON.parse(s.tagName==='TEMPLATE'?s.innerHTML:s.textContent)}})()")


def json_paths(obj, want, limit=15, keys_only=False, _path="", _out=None):
    """Where something lives in a big JSON: paths to keys (and strings) containing `want`.
    For ytInitialData and internal API responses nested dozens of levels deep.
    keys_only=True searches key names only: on hh a string search for "vacancies" drowned
    in footer links (23.09.2026). Lists and dicts show their size."""
    out = [] if _out is None else _out
    if len(out) >= limit:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{_path}.{k}" if _path else k
            if want.lower() in str(k).lower():
                size = f" [{len(v)}]" if isinstance(v, (list, dict)) else ""
                out.append(p + size)
            json_paths(v, want, limit, keys_only, p, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            json_paths(v, want, limit, keys_only, f"{_path}[{i}]", out)
    elif not keys_only and isinstance(obj, str) and want.lower() in obj.lower():
        out.append(f"{_path} = {obj[:60]!r}")
    return out[:limit]
