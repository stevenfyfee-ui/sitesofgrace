# Future Saints search (kids-safe)

Behind `SOG_FUTURE_SAINTS`, like every Future Saints page. Code: `future_saints/search.py`, the two
routes on `FutureSaintsHomePage`, `includes/_search_box.html`, `search_page.html` and the "Search"
block in `future-saints.js`.

## What it searches

Only **published** Future Saints pages under the Future Saints home:

- the five learning types;
- the California Missions hub;
- the projects guide;
- each Build This Mission project whose status is Published (it links to the mission page's `#build`).

Never adult pages, never drafts. A live page's database row is its published version, so a draft
edit isn't searchable until it's published. The adult site search (`search/views.py`) still
excludes Future Saints pages, and Future Saints search never touches it.

## The index

One small JSON list, one entry per page:

| Key | What |
|---|---|
| `t` | Title (the student title) |
| `k` | Group: one of the five types, or `project` |
| `s` | Subtitle (for a project: its mission's title) |
| `p` | Place: the canonical page's locality and country; for a saint, the map place |
| `w` | The Words to Know words |
| `i` | The first sentence of the intro |
| `u` | URL |
| `m` | The World Discovery Map story to select (`""` when it isn't on the map) |
| `n` | Short name, for the empty state's suggestions |

- It is cached for 10 minutes and dropped on every publish or unpublish of a Future Saints page, or of
  a saint or sacred site page (`FutureSaintsConfig.ready`).
- **One limit:** the site has no shared cache, so each server process keeps its own copy. Publishing
  clears it at once in the process that handled the publish; the others pick up the change within
  10 minutes.
- `GET /future-saints/search/index/` returns `{"groups": [...], "entries": [...]}`, noindex. The
  browser fetches it once, the first time a search box gets focus.

## Matching (the same in Python and JavaScript)

- Accents and case are ignored ("fatima" finds Fátima).
- Every word typed must match the **start** of a word in the entry ("san die" finds San Diego;
  "rdes" finds nothing).
- A word of 5 or more letters may be one letter off: changed, added or missing ("lurdes",
  "loordes"). Shorter words must match exactly.
- Ranking: a title match counts most, then the place, then the subtitle, words and intro.

## Where it appears

- **Homepage:** a box under the hero, labelled "Search for a saint, a miracle, or a place", with the
  placeholder "Try Carlo, Fátima, or San Diego".
- **World Discovery Map:** a box above the filters.
  - Choosing a story selects it and zooms to it. A type that's filtered off is shown again.
  - A mission zooms to the California callout.
  - A story with no pin selects its card and shows "This story isn't on the map yet."
- **Header:** a search icon (aria-label "Search") on every Future Saints page, linking to the results
  page.

## Results page

`/future-saints/search/?q=` is server-rendered, so search works without JavaScript. It is always
noindex (the meta tag and the `X-Robots-Tag` header).

- Results are cards grouped by type, in the header nav's order, then Build This Mission.
- With no match it says "No stories found. Try another word!", followed by three suggestion links.
  These are the placeholder's words that find something, then published story names.

## Accessibility

- Without JavaScript, the field is a plain search input in a GET form.
- With JavaScript it becomes an ARIA 1.2 combobox: the arrow keys move through the suggestions,
  Enter opens one, and Escape closes the list (or clears the field).
- A polite live region announces the count, or "No stories found. Try another word!".
- Every target is at least 44 px.

## Privacy

Nothing about a search is stored or sent anywhere:

- no query logging;
- no Wagtail search promotions or hit counts;
- no analytics, cookies or browser storage.

While typing, the query never leaves the browser; the only request is the one fetch of the index.
`test_search` checks that a search writes nothing to the database and sets no cookie, and that the
type-ahead code uses no storage, cookies, beacons or analytics.
