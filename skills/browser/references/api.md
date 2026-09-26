# Site APIs: what was found

Captured 23.09.2026 from the agent Chrome without login. Internal APIs are promised to nobody:
versions in the paths (`v2.10`) change, fields move. A recipe here is a first attempt; if it
fails, `sniff()` again and fix the entry.

## Reading `sniff()`

```
5756.493  GET  200 application/json   38.5KB  https://api.vc.ru/v2.10/feed?...&cursor=...
```

`id` (for `api_body`), method, status, response type, size, URL, POST body. Ads, analytics,
pixels and player media are dropped (`noise=True` shows everything). If the page requested
nothing on load, the data came with the HTML: check `embedded_json()`. A feed that loads on
scroll: `sniff(lambda: (js("scrollTo(0, document.documentElement.scrollHeight)"), time.sleep(1.5)))`.

## hh.ru

- Public `api.hh.ru/vacancies` from our network: curl got `403`, a retry hung for 15 s, from
  the page `Failed to fetch`. Cause not established; guess: the VPN exit is not allowed.
- Results are rendered server-side, no separate XHR. The whole state is in
  `embedded("template#HH-Lux-InitialState")` (599 KB): `vacancySearchResult.vacancies`
  (50 items with `name`, `company.name`, `compensation`, `area`, `address`, `creationTime` and
  dozens more). Pages: `&page=N` in the URL and `embedded` again.
- `hh.ru/api/fl` and `adsrv.hh.ru` are anti-fraud and ads, not data.

## habr.com

- Search: `GET https://habr.com/kek/v2/articles/?query=…&order=relevance&fl=ru&hl=ru&page=N&perPage=20`.
  Response: `publicationIds` (order) and `publicationRefs[id]` (`titleHtml`, `timePublished`,
  `statistics.score`, `statistics.readingCount`), `pagesCount`. One page in 1 s.
- `titleHtml` contains highlight markup `<em class="searched-item">`; strip tags.
- The search page makes no request until the icon is clicked (see sites.md), but `fetch_json`
  on the URL above works right away.

## vc.ru

- Feed: `GET https://api.vc.ru/v2.10/feed?markdown=false&sorting=hotness&cursor=…&lastId=…&lastSortingValue=…`.
  Response `result.items` and `result.cursor`; the next page uses the cursor from the response.
  Take the first URL from `sniff` on scroll.
- Post: `GET https://api.vc.ru/v2.10/content?id=ID&markdown=false`.
- The page holds `window.__INITIAL_STATE__` (316 KB).
- `POST api.vc.ru/v2.4/content/read` marks a post as read: it writes, do not replay it.

## dzen.ru

- Search: `GET https://dzen.ru/api/web/v1/zen-search?country_code=ru&count_content=3&query=…&…&_csrf=…`.
  The URL carries `_csrf`, so take it from `sniff` on the same page and change only `query`;
  a replay with another query worked. Response `items[].title`, `items[].source.title`, `more`.
- The page holds `window.MICRO_APP_SSR_DATA` (36 KB).
- Noise: player video and audio from `okcdn.ru`, `telemetry.dzen.ru`, `yandex.ru/an/rtbcount`.

## youtube.com

- Search: `POST https://www.youtube.com/youtubei/v1/search?prettyPrint=false&key=KEY` with body
  `{"context": CONTEXT, "query": "…"}`, where `KEY = js("ytcfg.data_.INNERTUBE_API_KEY")` and
  `CONTEXT = js("ytcfg.data_.INNERTUBE_CONTEXT")` from any YouTube page. A replay with a new
  query returned results in 2.9 s.
- The page itself sends the body gzipped and `sniff` prints it as binary: build the body from
  the recipe above instead of copying it.
- Videos in the response: `…itemSectionRenderer.contents[i].videoRenderer` (`videoId`,
  `title.runs[0].text`, `ownerText`, `lengthText`, `viewCountText`). Find them with
  `json_paths(d, "videoRenderer", keys_only=True)`.
- The page holds `window.ytInitialData` (825 KB, first results) and `window.ytcfg` (560 KB).
- Not for transcripts: the transcript panel did not load without login. That is `video`.

## Marketplaces (checked 23.09.2026)

| Site | Best rung | Recipe |
|---|---|---|
| plati.market | API (other domain) | `sniff(..., pattern="cataloguer/front/products")` on `/search/QUERY`, then `fetch_json(url)` with default `credentials`; items in `content.items[]` (`name`, `price`, `seller_name`). `include` fails CORS. |
| playerok.com | API | `POST https://api.playerok.com/v1/catalog/items/top` body `{"filter":{},"page":{"size":20}}` via `replay`; `items[]` (`name`, `price`, `seller.username`, `game.name`), `endCursor`, `hasNextPage`. Site also uses GraphQL on `playerok.com/graphql`. |
| wildberries.ru | API with page headers | `sniff(..., pattern=r"u-search/exactmatch.*search\?")` on `/catalog/0/search.aspx?search=…`; `api_body` gives `products[100]` (`name`, `brand`, `id`, `sizes[0].price.product`/100 = rubles). Next page only via `replay(call, url=call["url"] + "&page=2")`: the page sends `deviceid`, `x-queryid`, `x-userid`, `x-spa-version`, a bare fetch got `403`. Pages 1 and 2 overlapped by 2. |
| ozon.ru | embedded widget | A search for "наушники" redirected to a category. Results are in `[id^="state-tileGridDesktop"]` `data-state` JSON: `items[]`, price `mainState[0].priceV2.price[0].text`, title `mainState[1].textDS.text`, `sku`. Only the first screen (8 items) is there; the rest loads on scroll through `entrypoint-api.bx/page/json/v2?url=…`. `cards(r"ozon\.ru/product/")` gave 16. |
| market.yandex.ru | DOM | Almost no XHR, `ld+json` is only `WebSite`. `cards(r"market\.yandex\.ru/(product|card)")`: 8 cards with title and specs; snippet root `[data-zone-name="productSnippet"]`. No CAPTCHA at this pace. |
| funpay.com | DOM | Server-rendered, no XHR, no embedded JSON. Categories: `links(r"funpay\.com/(lots|chips)/\d+/?$", min_text=2, limit=3000)` (alphabetical, 3000+). Offers: `a.tc-item` with `.tc-desc-text`, `.tc-price`, `.media-user-name`; "Робуксы" `/chips/99/` had 619 offers. |
| ggsel.net | DOM | `window.__RQ_R_…` (React Query state) has a random key and was absent on the next visit: do not rely on it. `cards(r"ggsel\.net/catalog/product/")` on `/catalog/steam`: 40 cards with title, rating, sales, price. |
