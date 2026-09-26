# Runs inside browser-harness (helpers are already in the namespace). Launch: scripts/selftest.py
# Form labels and values are Cyrillic on purpose: Cyrillic input is part of what is tested.
import os
import time

FORM = os.environ["BRAUZER_FORM_URL"]
fails = []


def check(name, ok, got=None):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  (got {got!r})"))
    if not ok:
        fails.append(name)


s = go(FORM, text=0)
ref = {it["label"]: it["ref"] for it in s["items"]}
check("snapshot sees 12 controls in the viewport", len(s["items"]) == 12, [it["label"] for it in s["items"]])
check("cursor:pointer div listed as clickable", "Подсказка без роли" in ref, list(ref))
check("checkbox label not duplicated", sum(1 for it in s["items"] if "Согласен" in it["label"]) == 1)
rej = next((it for it in s["items"] if it["label"] == "Отклонить все"), None)
check("label = visible text, aria as extra", rej is not None and rej.get("aria") == "Запретить использование cookie", rej)
check("hidden role=dialog does not raise the flag", s["dialog"] is False, s["dialog"])
check("offscreen control not in the snapshot", "Далеко внизу" not in ref, list(ref))
check("no CAPTCHA reported while the widget is hidden", s["captcha"] == [], s["captcha"])
cs = cards(r"/item/\d+")
check("cards: one card per item across img/title/buy links", len(cs) == 2, [c["lines"] for c in cs])
if len(cs) == 2:
    check("cards: title, price and button in one card",
          cs[0]["lines"] == ["Наушники Альфа", "1 151 ₽", "Купить"] and "Бета" in cs[1]["lines"][0], cs[0]["lines"])
ls = links(r"\?v=1", min_text=1)
check("links: longest text of two links to one URL",
      len(ls) == 1 and ls[0]["text"] == "Длинный заголовок видео про агента", ls)

got = fill(ref["Имя"], "Ёжик Иванов")
check("fill: Cyrillic verbatim", got == "Ёжик Иванов", got)
got = pick(ref["Город"], "санкт")
check("pick: by substring", got == "Санкт-Петербург", got)
check("pick: exactly one change event", js("window.changes()") == 1, js("window.changes()"))
act(ref["Согласен"])
check("act: checkbox", js("agree.checked") is True)
got = fill(ref["Заметка"], "привет, мир")
check("fill: contenteditable", got == "привет, мир", got)
got = fill(ref["Телефон"], "1234567")
check("fill: maxlength not bypassed", got == "12345", got)
got = fill(ref["Телефон"], "1234567", force=True)
check("fill: force bypasses", got == "1234567", got)
act(ref["Подсказка без роли"])
check("act: clickable", js("log.textContent") == "sugg-clicked", js("log.textContent"))
act(ref["Готово"])
check("act: button sees form values", js("log.textContent") == "sent:Ёжик Иванов|spb|true", js("log.textContent"))

js("ov.style.display='block'")
try:
    act(ref["Готово"])
    check("act: overlay stops the click", False, "click went through")
except StaleRef as e:
    check("act: overlay stops the click", False, str(e))
except RuntimeError as e:
    check("act: overlay stops the click", "covered by" in str(e), str(e))
js("ov.style.display='none'")

js("const b=document.querySelector('button'); b.replaceWith(b.cloneNode(true))")
try:
    act(ref["Готово"])
    check("act: replaced node raises StaleRef", False, "click went through")
except StaleRef:
    check("act: replaced node raises StaleRef", True)

js("hid.style.display='block'")
check("visible role=dialog raises the flag", snap(text=0, quiet=True)["dialog"] is True)
js("hid.style.display='none'")
far = find("далеко")
check("find: sees an offscreen control", len(far) == 1, far)
if far:
    try:
        act(far[0])
        check("act: click on an offscreen control", True)
    except Exception as e:
        check("act: click on an offscreen control", False, f"{type(e).__name__}: {e}")

# --- act() reports what the click changed; a native dialog does not hang the helpers
got = act(find("Пустая кнопка")[0])
check("act: a no-op click reports nothing changed", got == [], got)
got = act(find("…ещё")[0])
check("act: expander reports aria-expanded and the new text",
      "expanded false→true" in got and any(g.startswith("text +") for g in got), got)
got = act(find("Медленная")[0])
check("act: waits for a change that comes 700 ms later", any(g.startswith("text +") for g in got), got)
t = time.time()
try:
    got = act(find("Удалить")[0])
except Exception as e:  # the old failure: click_at_xy hung on the confirm for 5 s
    got = f"{type(e).__name__}: {str(e)[:80]}"
check("act: a confirm opened by the click is reported, not hung on",
      isinstance(got, list) and got and "confirm" in got[0] and time.time() - t < 3, (got, round(time.time() - t, 1)))
try:
    s = snap(text=0)
    ok = bool(s["native_dialog"]) and s["native_dialog"]["type"] == "confirm" and s["items"] == []
    got = s.get("native_dialog")
except Exception as e:  # the old failure: Runtime.evaluate timed out after 5 s
    ok, got = False, f"{type(e).__name__}: {str(e)[:80]}"
check("snap: native dialog reported instead of a 5 s timeout", ok, got)
try:
    nav(FORM)
    check("nav: refuses while a native dialog is open", False, "navigated")
except DialogOpen:
    check("nav: refuses while a native dialog is open", True)
d = dialog()
check("dialog(): dismisses by default, the page got false",
      bool(d) and js("log2.textContent") == "confirm:false", js("log2.textContent"))
check("dialog(): None when nothing is open", dialog() is None)
got = act(find("Поздний алерт")[0])
check("act: an alert 600 ms after the click is caught too", bool(got) and "alert" in got[0], got)
dialog(accept=True)

# --- CAPTCHA: detect and wait for the user; the fake widget is hidden by a timer as if solved
js("scrollTo(0, 0); cap.style.display='block'")
check("captcha(): visible widget detected", captcha() == ["recaptcha"], captcha())
check("snap() reports the CAPTCHA", snap(text=0, quiet=True)["captcha"] == ["recaptcha"])
js("setTimeout(() => cap.style.display='none', 1500)")
t = time.time()
gone = wait_captcha_gone(timeout=10, poll=0.3)
check("wait_captcha_gone: returns once the user solved it", gone is True and time.time() - t < 6, round(time.time() - t, 1))
# kuper's ServicePipe reloads a fresh challenge every few seconds: a blink is not a solve
js("cap.style.display='block'; window.blink = setInterval(() => { cap.style.display='none';"
   " setTimeout(() => cap.style.display='block', 400); }, 1500)")
gone = wait_captcha_gone(timeout=5, poll=0.3)
js("clearInterval(window.blink); cap.style.display='none'")
check("wait_captcha_gone: a reloading challenge is not reported as solved", gone is False, gone)
js("spcap.style.display='block'")
got = captcha()
check("captcha(): a vendor not on the list is still caught (kuper ServicePipe)",
      got == ["captcha, unknown vendor: #spcap"], got)
js("spcap.style.display='none'")
check("captcha(): the visible reCAPTCHA v3 badge is not a CAPTCHA", captcha() == [], captcha())

# --- Data rungs: capture a page request, read the response, replay it; embedded JSON
calls = sniff(lambda: act(find("Загрузить")[0]), seconds=5)
hit = [c for c in calls if "data.json" in c["url"]]
check("sniff: caught the page fetch", len(hit) == 1 and hit[0]["status"] == 200, calls)
if hit:
    body = api_body(hit[0]["id"])
    check("api_body: response JSON from the browser", isinstance(body, dict) and len(body.get("items", [])) == 40, str(body)[:80])
    again = fetch_json(hit[0]["url"].replace("page=1", "page=2"))
    check("fetch_json: replay with other params", isinstance(again, dict) and again.get("cursor") == "abc", str(again)[:80])
    again = replay(hit[0], url=hit[0]["url"].replace("page=1", "page=3"))
    check("replay: same request, another page", isinstance(again, dict) and len(again.get("items", [])) == 40, str(again)[:80])
    check("sniff: request headers recorded for replay", isinstance(hit[0].get("headers"), dict) and hit[0]["headers"], hit[0].get("headers"))
    try:
        fetch_json(hit[0]["url"].split("data.json")[0] + "nope.json")
        check("fetch_json: 404 raises", False, "no error")
    except RuntimeError as e:
        check("fetch_json: 404 raises", "404" in str(e), str(e)[:80])
check("act on the load button reached the page", js("log.textContent") == "loaded:40", js("log.textContent"))
found = embedded_json()
check("embedded_json: found a JSON <template>", any(f["where"] == "template#state" for f in found), found)
st = embedded("template#state")
check("embedded: parsed the state", len(st["search"]["results"]) == 30, str(st)[:80])
got = json_paths(st, "results", keys_only=True)
check("json_paths keys_only: path and size", got == ["search.results [30]"], got)

try:
    act(find("Следующая страница")[0])
    check("act: link navigation waits for the page", js("location.search") == "?page=2", js("location.search"))
except Exception as e:
    check("act: link navigation waits for the page", False, f"{type(e).__name__}: {e}")

# --- Pagination (tests/list.html): traps from hh, habr, vc and funpay, see the comment there
LIST = FORM.replace("form.html", "list.html")
OFFER = r"offer\?id=\d+"
go(LIST + "?mode=pages&page=1", text=0, quiet=True)
cs = cards(OFFER)
check("cards: ids in the query are separate items (funpay)", len(cs) == 15, len(cs))
nx = pager(OFFER, quiet=True)
check("pager: page number after the active one, header link ignored",
      bool(nx) and nx[0]["kind"] == "next" and nx[0]["href"].endswith("page=2"), nx)
r = paginate(OFFER, pages=10, pause=0, wait=3)
check("paginate pages: overlap deduped, 33 unique", len(r) == 33, len(r))
check("paginate pages: reached page 3 and stopped when the pager ended",
      js("location.search").endswith("page=3") and "gone" in r.stopped, (js("location.search"), r.stopped))

go(LIST + "?mode=feed", text=0, quiet=True)
check("pager: widget button before the list is not the list's (vc)", pager(OFFER, quiet=True) == [], pager(OFFER, quiet=True))
r = paginate(OFFER, pages=10, pause=0, wait=3)
check("paginate feed: scrolled until the feed ended", len(r) == 35 and "end of the list" in r.stopped, (len(r), r.stopped))

go(LIST + "?mode=more", text=0, quiet=True)
r = paginate(OFFER, pages=10, pause=0, wait=3)
keys = {c["key"].split("id=")[-1] for c in r}
check("paginate more: button pressed until it disappeared", len(r) == 35 and "gone" in r.stopped, (len(r), r.stopped))
check("paginate more: the widget's own button left alone", "9003" not in keys, sorted(keys)[-3:])

go(LIST + "?mode=loop", text=0, quiet=True)
r = paginate(OFFER, pages=10, pause=0, wait=3)
check("paginate: 'next' to the same page stops the walk", "visited" in r.stopped and len(r) == 15, (len(r), r.stopped))

print(f"\n{'ALL GREEN' if not fails else f'FAILURES: {len(fails)}'}")
raise SystemExit(1 if fails else 0)
