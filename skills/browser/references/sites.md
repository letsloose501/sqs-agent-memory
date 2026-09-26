# Site notes

Captured 23.09.2026 from the agent Chrome without login, VPN exit in Europe (YouTube showed
region LV). Sites change their markup: a selector here is a first attempt, not a fact. If it
fails, check with `find()`/`links()` and fix the entry.

Timing: `nav` includes loading and `settle()`; a snapshot costs 0.01-0.07 s, a screenshot 0.1-0.5 s.

## Pagination by site (24.09.2026, `paginate`, 3 rounds each)

| Site | How the list goes on | Call | Result |
|---|---|---|---|
| hh.ru | page numbers, active one `aria-current="true"` | `paginate(r"hh\.ru/vacancy/\d+")` | 3 pages in 19 s, then `.stopped` = "control is gone: last page" |
| habr.com | `a[rel=next]` "Туда" → `/pageN/` | `paginate(lambda: links(P), after=P)`, `P = r"habr\.com/ru/(companies/[^/]+/)?articles/\d+/$"` | 24 → 64 in 13 s |
| ggsel.net | "Показать ещё" under the grid, renders a moment after `settle()` | `paginate(r"ggsel\.net/catalog/product/")` | 60 → 186 in 11 s |
| funpay.com | "Показать ещё предложения", +200 per click | `paginate(r"funpay\.com/lots/offer")` | 199 → 500 in 19 s |
| vc.ru | infinite feed, +10-13 per scroll | `paginate(r"vc\.ru/[a-z0-9_-]+/\d+-")` | 17 → 51 in 4 rounds; the feed API in api.md is faster |

## hh.ru

- Search by URL: `/search/vacancy?text=…&area=113&experience=noExperience&page=N`.
- The home page form opens a login modal; closing it continues the search.
- Card: `[data-qa="serp-item__title"]`, employer `vacancy-serp__vacancy-employer-text`,
  address `vacancy-serp__vacancy-address`, salary: a `span` with `₽`.
- Results re-rank between requests, pages overlap. Dedupe by URL without query.
- Cookie banner with only "Понятно": leave it.

## habr.com

- `/ru/search/?q=…&target_type=posts` opens the form **without results**: click the search icon
  (`find("Поиск")`, role `clickable`), then `wait_for_element("article")`. After the click,
  5 articles in 1.6 s.
- Article links: `links(r"habr\.com/ru/(articles|companies/[^/]+/articles)/\d+/?$")`.
  Not `cards()`: snippets link to other articles, so the climb stops early and 25 articles gave
  7 scraps like `['В']` (24.09.2026).
- Article text: `#post-content-body` (6,000 chars on the test article; `main` is wider and
  includes the header).
- An ad toast at the bottom covers some controls.

## vc.ru

- Home: `links(r"vc\.ru/[a-z0-9_-]+/\d+-")` gives posts. `nav` about 4 s.
- Post text: `article` (`main` is empty).

## dzen.ru

- Entry goes through `sso.passport.yandex.ru/push`; once it returned `ERR_EMPTY_RESPONSE` and
  a `chrome-error://` page replaced the site. The second attempt worked.
- Search: `/search?query=…`, articles `links(r"dzen\.ru/a/")`. Links carry a `?feed_exp=…`
  tail; strip the query for dedupe.
- Article text: `[itemprop=articleBody]` (`article` is empty, `main` includes the channel header).
- WebFetch refuses dzen, the browser gets it.

## youtube.com

- First visit: cookie consent, button "Отклонить все" (aria "Запретить использование файлов
  cookie…"). The choice persists in the profile.
- Search: `/results?search_query=…`, videos `links(r"/watch\?v=")`.
- The DOM always holds hidden `role="dialog"` nodes; the snapshot checks visibility.
- A video page may play a 20 s pre-roll; it does not affect the snapshot.
- "Ещё" on the actions and "...ещё" on the description are different buttons. Expanded state:
  `#description-inline-expander[is-expanded]`.
- Transcript: "Показать текст видео" opens `engagement-panel-searchable-transcript`, but without
  login it spun for 10 s and delivered nothing. Use the `video` skill for transcripts.

## studwork.ru

- curl gets `403` from Cloudflare ("Just a moment..."), the browser gets through.
- `/info/calendar` redirects to `/login?returnUrl=…`: behind login.

## kuper.ru (26.09.2026)

**Use a script, not the browser:** a curl_cffi script against the internal API below (memory
`kuper-python-collector`) gave prices through the same VPN in seconds, while the browser was
stopped twice. What the browser run found, for when the script needs to grow:

- First visit from the agent profile: ServicePipe anti-bot page `/xpvnsulc/` with a "rotate the
  picture" CAPTCHA (`servicepipe-rotate`). The user solves it; the page reloads a fresh challenge
  every few seconds, so one empty poll is not a solve. After it: redirect to `web.kuper.ru`.
- A city dialog ("Ваш город Москва?") covers the page on every navigation; `press_key("Escape")`
  closes it without choosing. The cookie banner has only "Соглашаюсь": leave it.
- Search by URL: `/multisearch?q=…`, results grouped by store. Internal API:
  `GET /api/v3/mweb/multisearch-products?lat=&lon=&verticals=ALL&q=…`; without an address the
  coordinates are central Moscow (55.7588, 37.6178).
- Adding to cart needs a delivery address: "Добавить товар в корзину" opens the "Новый адрес"
  dialog with a 2GIS map, nothing lands in the cart. Entering an address is the user's decision.
- Ten minutes later a return to `/multisearch` got a block page "Отключите VPN" (no CAPTCHA,
  buttons "Обновить" / "Скопировать"), the IP was a VPN exit. The script was not
  blocked on the same IP at the same time.
- Catalogue volumes lie: `human_volume` "930 л" and "800 г" for 930 ml / 800 ml milk; the
  product name is right. `kuper.py` trusts the name when they disagree.
