# Pilgrimage Platform v2 — Phase 0 findings

Read-only survey of the codebase on branch `pilgrimage-v2` (created from main at `e3dc64d`),
written 2026-10-21. Paths are repo-relative. Line numbers are from that commit.
Database facts come from the **local copy (Aug 2026)**, never from production.

Mockup: `docs/mockups/sites-of-grace-v2-mockup.html` (copied from Downloads; 1,047 lines).

---

## Step 2 — branch and deploy check

- Local `main` == `origin/main` == `e3dc64d`. The tree was cleaned by deleting the duplicate
  `tools/saints_import_2026-10_1.json` (approved) before branching.
- Only `main` deploys. The live App Platform spec (read with `doctl apps spec get`, branch fields
  only) has three components, all `github.repo: stevenfyfee-ui/sitesofgrace`,
  `branch: main`, `deploy_on_push: true`: service `sitesofgrace`, PRE_DEPLOY job `migrate`,
  SCHEDULED job `fetch-news`. `.do/app.yaml` in the repo is marked stale/non-authoritative
  but agrees. There is no `.github/` (no Actions). Pushing `pilgrimage-v2` deploys nothing.
- Autopush: `AUTOPUSH-BLOCKED.txt` absent. `.autopush-pause` already existed and is left in place.
  See **Follow-ups** for the branch-guard gap.
- `prod.dump` was never committed (`git log --all -- prod.dump` empty), was gitignored by
  `*.dump` (`.gitignore:25`), and has been deleted.

---

## a. SacredSitePage

`catalog/models.py:204` — `class SacredSitePage(RoutablePageMixin, Page)`. No `parent_page_types`,
`subpage_types` or Meta. No field sets `verbose_name`.

### Every own field

| Line | Field | Type |
|---|---|---|
| 205 | `category` | CharField(40, choices=CATEGORY_CHOICES), **required** |
| 206 | `canonical_status` | CharField(60, blank, choices=CANONICAL_STATUS_CHOICES) |
| 207 | `locality` | CharField(160, blank) |
| 208 | `country` | CharField(120, blank) |
| 209 | `latitude` | DecimalField(9,6, null, blank) |
| 210 | `longitude` | DecimalField(9,6, null, blank) |
| 211 | `date_display` | CharField(160, blank) — free text, e.g. event year/range |
| 212 | `feast_day` | CharField(120, blank) — free text |
| 213 | `summary_short` | TextField(blank) |
| 214 | `the_story` | RichTextField(blank) |
| 215 | `church_recognition` | RichTextField(blank) |
| 216 | `catholic_teaching` | RichTextField(blank) |
| 217 | `pilgrimage_info` | RichTextField(blank) — legacy, not displayed |
| 218 | `go_deeper` | RichTextField(blank) |
| 219 | `associated_saint` | FK SaintPage, null, SET_NULL, related_name `sites` |
| 228 | `related_saints` | ParentalManyToMany SaintPage, related_name `related_sites` (never rendered on the site page) |
| 236 | `featured_image` | FK wagtailimages.Image, null, SET_NULL |
| 243 | `topics` | ParentalManyToMany catalog.Topic, related_name `sites` |
| 244 | `location_link` | URLField(blank, max 200) |
| 245 | `notes_internal` | TextField(blank) |
| 272–281 | `quick_ideal_stay`(40), `quick_ideal_stay_note`(60), `quick_best_months`(40), `quick_best_months_note`(60), `quick_airport`(60), `quick_airport_note`(60), `quick_language`(60), `quick_language_note`(60), `quick_accessibility`(40), `quick_accessibility_note`(60) | CharField, blank |

Related models: `SiteTravelSection` (l.596, ParentalKey `travel_sections`, `kind` choices,
`teaser` 90, `body` rich, unique per page+kind); `TrailStop.site` (`trail_stops`);
`pilgrims.PilgrimPhoto.site` (`pilgrim_photos`, PROTECT); `pilgrims.SiteVisit.site`
(`pilgrim_visits`, statuses `visited` / `want_to_go`); pilgrim posts `site` (`pilgrim_posts`);
`planner.DestinationCost.associated_sites` (`destination_costs`).

### Where each concept lives

| Concept | Field |
|---|---|
| Address | **None.** No address field exists. Only `locality` + `country`. |
| Official website | `location_link` (misnamed; template prints "Visit the official website ↗", `sacred_site_page.html:85`). Trail pages use a properly named `official_url`. |
| Coordinates | `latitude`, `longitude` (Decimal; no PostGIS point) |
| Country / locality | `country` / `locality` |
| Principal saint | `associated_saint` (FK); secondary: `related_saints` |
| Significance / summary | `summary_short` (sites have no `significance`; that is SaintPage only) |
| Feast day | `feast_day` |
| Story | `the_story` |
| Church recognition text | `church_recognition` |
| Church / canonical status | `canonical_status` |
| Quick Card | the ten `quick_*` fields, plus `feast_day` as a cell |

### Status values

`CANONICAL_STATUS_CHOICES` (`catalog/models.py:98–108`), value == label: `Nihil obstat`,
`Prae oculis habeatur`, `Curatur`, `Sub mandato`, `Prohibetur`,
`Declaratio de non supernaturalitate`, `Not Applicable`, `Recognized Devotion`,
`Constat de supernaturalitate (legacy)`; blank allowed. Importers blank unknown values
(`import_catalog.py:315–320`, `import_trails.py:215–220`).

Other status-like values: `SaintPage.data_status` (sites have none): `""` (graduated),
`stub-*` prefix (`stub_saints.py:16`), `stub-calendar`/`stub-canonization`
(`tools/saints_data/merge.py`). `PhotoReport` status: `open` / `actioned` / `dismissed`.
`SiteVisit` status: `visited` / `want_to_go`.

### Templates that can print "Not Applicable"

Exactly one: the hero badge, `catalog/templates/catalog/sacred_site_page.html:28`,
`{% if page.canonical_status %}<span class="badge badge-status">{{ page.canonical_status }}</span>{% endif %}`.
It prints whenever `canonical_status == "Not Applicable"`, which is the value on all 21
California Mission Trail sites (`catalog/data/california-mission-trail.json`) and 2 of 3 in
`catalog/data/new-sites-2026-09.json`. No Python builds display text containing it; no
"N/A" anywhere outside vendor JS. (Candidate ALWAYS-ON fix: suppress the badge for that value.)

---

## b. Page types, categories, CATEGORY_STYLES

| App | Page type | Constraints |
|---|---|---|
| home | `HomePage` (home/models.py:80) | max 1; subpage_types AboutPage, MapPage, StandardPage, StorePage, SupportPage, blog.BlogIndexPage |
| home | `StandardPage` (483) | unrestricted; `layout` = default / explore_hub / category_directory / saints_directory |
| home | `MapPage` (602) | max 1, slug `interactive-map` |
| home | `StorePage` (615), `AboutPage` (727), `SupportPage` (1182) | About/Support: parent HomePage, max 1 |
| catalog | `SaintPage` (127), `SacredSitePage` (204), `PilgrimageTrailPage` (641) | unrestricted |
| blog | `BlogIndexPage` (blog/models.py:169), `BlogPostPage` (335) | |
| learning | `LearnPage` (learning/models.py:22) | |
| planner | `PlanPage` (planner/models.py:104) | max 1 |
| store | `StoreIndexPage` (store/models.py:345) | max 1 |

`HomePage.subpage_types` omits PlanPage, LearnPage, StoreIndexPage and catalog types; they can only
be created under the unrestricted StandardPage. A new v2 `DestinationHubPage` will need its
parent/subpage rules decided explicitly.

`CATEGORY_CHOICES` (`catalog/models.py:23–29`): `Marian Apparition`, `Eucharistic Miracle`,
`Saints & Tombs`, `Holy Land`, `Shrine & Basilica`.

`CATEGORY_STYLES` — defined once in Python, `catalog/models.py:34–41`, imported by
`home/models.py:42` (→ `HUB_CARD_STYLES`, l.65–78, keyed by category-page slug), `search/views.py:86`,
and `nearby_sites`:

| Category | fill | stroke | dot |
|---|---|---|---|
| Marian Apparition | #FDF9F2 | #032553 | #032553 |
| Eucharistic Miracle | #C79A42 | #C79A42 | #FDF9F2 |
| Saints & Tombs | #032553 | #032553 | #C79A42 |
| Holy Land | #F9F1E8 | #C79A42 | #C79A42 |
| Shrine & Basilica | #173A61 | #173A61 | #FDF9F2 |
| default | #173A61 | #173A61 | #FDF9F2 |

**The map does not use these.** `sitesofgrace/templates/home/map_page.html:51–58` hard-codes its own
`CATEGORY_STYLES` (fill/stroke only), and 5 of 6 values differ:
Marian `#FFFFFF/#032553`, Eucharistic `#C79A42/#8A6A24`, Saints `#032553/#021A3B`,
Holy Land `#F3E4CE/#C79A42`, Shrine `#173A61/#0D2440`, default `#173A61/#0D2440`.
The comment at `catalog/models.py:31–33` cites a stale path (`home/templates/home/map_page.html`).
**The mockup uses a third set** (see m.1).

---

## c. Sacred site page template structure

`catalog/templates/catalog/sacred_site_page.html` (extends `base.html`). `get_context`
(models l.554–560) adds `map_page`, `gallery_preview_photos` (first 8), `gallery_total_count`.

Render order today:

1. Flash (l.14–20) when `?photos_added=N` (echoes the raw query value, autoescaped).
2. Hero `header.catalog-hero` (l.23–47): h1; badges (`category`, `canonical_status`); meta line
   "locality, country · date_display · Feast day: X"; `summary_short`; `associated_saint` link;
   `{% journey_buttons page %}` (Want to go / Visited); "Plan a trip here" → `/plan/?site=<slug>`;
   `includes/_trail_band.html` ("Stop N of M" per live trail).
3. `div.section-layout`, with `section-layout--with-nav` only when `page.section_nav|length > 1`
   (regression guard, `WithNavGateTests`, catalog/tests.py:146).
   - **Rail**: `sitesofgrace/templates/includes/_section_nav.html with sections=page.section_nav`.
   - **Main column**, in order: `featured_image`; the `page.body_blocks` loop (narrative sections,
     with Plan Your Visit inserted); topics tags; **Location** `#location` (official-website link +
     "See it on the interactive map →" `<map>?site=<slug>`); **Pilgrim Photos**
     `#pilgrim-photos` (always); **In the Area** (`_nearby_band.html`).

### Section rail

- `NARRATIVE_SECTIONS` (`catalog/models.py:339–347`): (`the-story`, The Story, `the_story`),
  (`church-recognition`, Church Recognition, `church_recognition`),
  (`catholic-teaching`, Catholic Teaching, `catholic_teaching`), (`go-deeper`, Go Deeper, `go_deeper`).
- `narrative_sections` (l.350) keeps filled ones; `body_blocks` (l.417) inserts `{"kind": "plan"}`
  right after catholic-teaching when `has_plan_section` — **if Catholic Teaching is empty, Plan Your
  Visit falls to the end, after Go Deeper.**
- `section_nav` (l.435): one entry per block; Plan Your Visit carries children (one per travel
  section); `location` appended when `has_location_section`. Pilgrim Photos, In the Area, topics
  and the trail band are **not** in the rail.

### Plan Your Visit

`catalog/templates/catalog/includes/_plan_your_visit.html`, `section#plan-your-visit`: Quick Card,
toolbar ("Expand all", `static/js/plan-your-visit.js`), then `.plan-cluster` groups of
`<details class="plan-panel" id="<kind>">` (number, label, teaser, body).
`catalog/travel_sections.py`: `TRAVEL_CLUSTERS` (l.15) is the source of truth —
plan-the-trip (how-long-should-i-stay, best-time-to-visit, getting-there), on-the-ground
(getting-around, where-to-stay, accessibility), what-to-do (most-important-things,
suggested-itinerary, mass-confession-prayer), practical (what-to-bring, before-you-go,
additional-information). `TRAVEL_SECTION_CHOICES` (l.38, 12 entries), `TRAVEL_LABELS`,
`TRAVEL_ORDER` (l.47). `plan_clusters` (models l.363) numbers only rendered panels.

### Quick Card

Inside `_plan_your_visit.html` (l.17–35), gated by `page.show_quick_card` (≥2 filled cells).
`quick_card_cells` (l.399): Ideal stay, Best months, Nearest airport, Language & currency,
Feast day (`feast_day`), Accessibility. Footer: "Estimate the cost of this trip →"
`/plan/?site=<slug>`. **Gotcha: a site with zero travel sections never shows the Quick Card**,
because the card lives inside the plan include.

### In the Area

`catalog/templates/catalog/includes/_nearby_band.html`, gated by `page.nearby_sites`; h2 "In the Area",
subtitle "Other sacred sites within 40 miles." (40 hard-coded); `nearby-chip` with an inline-styled dot,
title and miles. Last block on the page today.

### Pilgrim Photos

- Section: `sacred_site_page.html:98–123`. Data: `public_photos_queryset()` (models l.542) =
  `PilgrimPhoto(site=self, is_public_on_site=True, hidden_by_staff=False)` newest first;
  preview 8 (`GALLERY_PREVIEW_COUNT`). Empty state invites the first upload.
- Gallery: `{% routablepageurl page 'gallery_view' %}` → `<site url>gallery/` (route l.562–563,
  404 if not live, 24 per page), template `catalog/templates/catalog/sacred_site_gallery.html`
  (report form → `pilgrims:report_photo`; staff-only hide form, the only template `is_staff` check).
- Add photos: signed in → `{% url 'pilgrims:photo_upload' %}?site=<slug>` (`/pilgrims/photos/upload/`,
  `pilgrims/views.py:434`, `@login_required`); signed out → "Sign in to add your photos"
  → `account_login?next=<path>`. Sharing publicly requires `can_share_photo`
  (`pilgrims/permissions.py:148`: verified email, `can_share_publicly`), 10 shares/day,
  100 uploads/hour; returns to the site page with `?photos_added=N`.
- Moderation is post-hoc (`pilgrims/moderation.py apply_auto_hide_policy`): one sexual /
  minor-safety / violence report hides immediately; other reasons need 2 distinct reporters,
  deduplicated by `reporter_ip_hash` (hash, never the raw IP; `pilgrims/models.py:560–566`).
- Position today: after Location, **before** In the Area. The mockup moves it to the very end.

---

## d. nearby_sites

`catalog/models.py:495–540`, `@cached_property` on SacredSitePage. Constants (l.49–51):
`NEARBY_RADIUS_MILES = 40`, `NEARBY_MAX_RESULTS = 8`, `EARTH_RADIUS_MILES = 3958.8`;
`miles_between()` (l.54) is a Python haversine.

Algorithm: `[]` if own lat/lng is None → bounding box (lat ±40/69°, lon ±40/max(69·cos lat, 1)) →
`SacredSitePage.objects.live().exclude(pk=self.pk)` within the box → haversine, drop > 40 mi →
sort ascending → first 8. Each entry: `{page, miles, miles_display ("<1" or rounded int), style}`.
Used only by `_nearby_band.html`. Tests: `NearbySitesTests` (catalog/tests.py:233–289) — radius,
ordering, no-coords, drafts excluded, chips render. Not tested: the cap of 8, `"<1"`, the pole floor.
No drive-time data exists (the mockup's "about 20 min drive" has no source; see m).

---

## e. Map code

### Inventory

| File | What |
|---|---|
| `sitesofgrace/static/js/basemap.js` | `window.SoGBasemap = {add, maxZoom: 16}`. Two Esri Light Gray Canvas tile layers (`World_Light_Gray_Base` + `World_Light_Gray_Reference`), `maxZoom: 16`, attribution "Tiles © Esri — Esri, DeLorme, NAVTEQ". The only `L.tileLayer` calls in the project. No API key. |
| `sitesofgrace/templates/home/map_page.html` | Interactive Map (MapPage). Leaflet 1.9.4 from unpkg **with SRI**; then `community/js/journey_buttons.js`, `js/basemap.js`, `js/trails.js`, inline IIFE (l.39–307). |
| `sitesofgrace/static/js/trails.js` | `window.SoGTrails = {fetch, draw}`; dashed `L.polyline` in overlayPane + numbered `L.divIcon` stop markers; escapes HTML. |
| `catalog/templates/catalog/pilgrimage_trail_page.html:145–167` | Trail map: `L.map(el, {scrollWheelZoom:false})`, `fitBounds`; no site dots, no `radiusFor`. |
| `sitesofgrace/templates/pilgrims/profile_detail.html:175–221` | Passport map: own RED/WHITE colours by visit status, own `radiusFor` (min 5, max 9), no pane. |

The sacred site page has **no map** today (only a link to `/interactive-map/?site=<slug>`). The planner has no map.
`maxZoom: 16` is set only on the tile layers, never on `L.map`; Leaflet derives 16 from them.

### Interactive Map details

- Data: `fetch` of `/sacred-sites.json` (`catalog/views.py:7–35`, `sacred_sites_json`) and
  `/pilgrimage-trails.json` (`catalog/views.py:38–57`).
- Init `L.map(el).setView([20, 0], 2)` (l.87) → `SoGBasemap.add(map)` (l.88).
- Pane: `map.createPane('sitesPane').style.zIndex = 450` (l.93) — above overlayPane (400, trail lines),
  below markerPane (600, trail stop icons).
- `function radiusFor(z) { return Math.max(2.4, Math.min(7, 2.4 + (z - 2) * 0.62)); }` (l.66).
- Dots (l.277–283): `L.circleMarker(latlng, {pane:'sitesPane', radius: radiusFor(zoom),
  fillColor, color: stroke, weight: 1.1, opacity: 1, fillOpacity: 0.85})`.
- `zoomend` (l.263–266) resizes **all** markers, including filtered-out ones.
- Popups `popupHtml` (l.68–85): category badge, title, meta, summary, "Read more →", journey buttons.
  **Values are concatenated without HTML escaping** (admin-entered content, so low risk; but v2 code
  should escape). No tooltips, no permanent labels, no clustering.
- Legend: DOM (not `L.control`), category filter buttons, collapsed ≤640px, state in localStorage
  `sog-map-legend-collapsed` (try/catch). Text search via `.sog-search--map` events. `?site=<slug>` focuses a pin.

### Recommendation: `sitesofgrace/static/js/sog-maps.js`

An IIFE exposing `window.SoGMaps`, loaded after `basemap.js` and before page scripts:

- `CATEGORY_STYLES`, `DEFAULT_STYLE`, `categoryStyle(category)` — copied **verbatim from
  map_page.html's current values**, so the Interactive Map's pins don't change.
- `radiusFor(z)` (map curve) and `radiusCurve(min, max)` so the passport map keeps 5–9.
- `createSitePane(map)` → `'sitesPane'` at zIndex 450.
- `siteMarker(latlng, style, opts)` → circleMarker with the existing options; `pane` only if given.
- `bindRadiusOnZoom(map, getMarkers, radiusFn)` — takes a getter so the map page keeps resizing
  hidden markers.
- `escapeHtml` for new popups/tooltips.
- Optional `createMap(el, opts)` that calls `L.map(el, opts)` + `SoGBasemap.add` and adds nothing else.

Things that would silently change behaviour if shared naively: (1) using the Python colours;
(2) one radius curve for the passport; (3) forcing `sitesPane` on passport dots; (4) a zoom handler
that only iterates visible layers; (5) shared init defaults (trail map has `scrollWheelZoom:false`
and no `setView`); (6) `site.latitude/longitude` vs passport's `site.lat/lng` (take a latlng);
(7) escaping inside existing popups. Keep popups, legend, filters and passport colours page-local.

Migration of existing pages onto `sog-maps.js` should be its own step, verified in the console
before/after (`getMaxZoom`, pane zIndex, marker options, radii at z 2/5/9/13/16 =
2.4/4.26/6.74/7/7 on the map, 5/6.86/9/9/9 on the passport) plus screenshots.

---

## f. Homepage

`HomePage` (`home/models.py:80–203`), all `blank=True` unless noted:
`hero_heading`, `hero_intro`, `hero_image`, `primary_cta_text/link`, `secondary_cta_text/link`,
`featured_sites_heading`, `store_heading` (unrendered), `community_heading`, `community_intro`
(unrendered), `community_image`, `community_cta_text` (ignored by template) / `community_cta_link`,
`subscription_*` ×8 (unrendered, no panels), `calendar_enabled` (default True),
`calendar_heading`, `calendar_footer_link_text`, `calendar_footer_link` (FK Page),
`partners_heading`, `partners_quote`, `partners_quote_source`, `news_heading`, `news_intro`,
`news_enabled` (default True), `news_count` (default 6).
Inlines: `FeatureCard` (`feature_cards`, max 8), `FeaturedSite` (`featured_sites`, max 2),
`FeaturedSaint` (`featured_saints`, max 2), `JourneyBullet` (`journey_bullets`, max 6), `Partner`
(`partners`); `SubscriptionBullet`, `StorePick` unrendered.
Context (`get_context` l.273–309): `news_items`, `news_topics`, `news_last_updated` (unused),
`calendar_footer_url`, `liturgical`, `liturgical_panels`; `?_date=` honoured only in DEBUG.

Template `sitesofgrace/templates/home/home_page.html`, in order:

| # | Block | Lines | Fed by |
|---|---|---|---|
| 1 | Hero | 10–21 | `hero_image`, `hero_heading`, `hero_intro`, CTA fields; hard-coded `_search_bar.html` |
| 2 | Four image cards | 24–41 | `feature_cards` (four per row via `static/css/home.css:31`) |
| 3 | Three-column band | 44–143 | a) Featured Sites and Saints: `featured_sites_heading`, `featured_sites`, `featured_saints`, hard-coded "View all ›" → `/explore/`. b) Your Journey, Your Story: `community_heading`, `journey_bullets` (icons chosen by exact bullet title), `community_image`, button text hard-coded "Join Our Community" → `passport` if signed in else `community_cta_link`. c) Today in the Church: `home/includes/_today_in_church.html` when `calendar_enabled` (`liturgical`, `calendar_heading`, `calendar_footer_*`; JS `static/js/today-in-church.js`) |
| 4 | News | 146–148 | `home/includes/_news_feed.html` when `news_enabled and news_items` |
| 5 | Partners | 151–169 | `partners*` |
| 6 | Support band | 177–188 | `{% support_page %}` tag (`home/templatetags/support_tags.py`) |

The mockup keeps 1 and 2, removes 3 and 4, and adds "Where in the world?" (destinations) and
"Upcoming feasts". It does not show Partners or the Support band (see m).

---

## g. Liturgy

- `liturgical_today(now=None)` — `liturgy/today.py:249`. Returns `{"yesterday", "today", "tomorrow"}`
  of Day dicts (`_day()`, l.197–223): `date, iso, label, short_label, season_key, season, color,
  celebrations[{name, rank_label, color, page_url}], items[{title, url, kind, meta, image_id,
  thumbnail}], visible_items (3), more_count, upcoming`. Date from `liturgical_date()` (l.69) in
  `settings.LITURGICAL_TIME_ZONE` (base.py:242, America/Los_Angeles).
- Calendar data: committed JSON `liturgy/data/litcal-US-{year}.json` for **2026–2030 only**
  (from `manage.py sync_liturgical_calendar`); `celebrations_on(date)` (`liturgy/calendar.py:50`),
  per-year `lru_cache`. No network at request time.
- Matching (`liturgy/feasts.py`): `parse_feast_text` (l.116) turns free-text `feast_day` into
  `("fixed", m, d)` or `("movable", event_key)` (`MOVABLE_FEASTS` l.41–73, relative phrases skipped);
  `parse_anniversaries(date_display)` (l.136) for sites. `_build()` (l.180) indexes live SaintPage +
  SacredSitePage by (month, day) or event_key, plus `titles` (`fold()` in `catalog/text.py:18`) to
  link LitCal celebration names to pages. Per day, `today._items_for(day, events, index)` (l.152)
  returns linked celebrations, then saints, sites, anniversaries, deduped.
- Cache: `liturgy:day-index:v1`, 15 min (`feasts.py:17–18`), Django default cache. **No `CACHES`
  setting anywhere, so it's per-process LocMem.** `clear_day_index` runs on publish/unpublish of
  saints/sites (`liturgy/apps.py:24–26`) but only in the process that handled the publish; other
  workers can be stale up to 15 min.
- `audit_feast_dates`: read-only report of unparseable feast texts and empty days.

**"Next N feasts within D days that match a live saint or site"** — add
`upcoming_feasts(n, days, now=None)` in `liturgy/today.py`: from `liturgical_date(now)`, walk
`day + offset` for `offset in 0..D`, call `celebrations_on(day)` and `_items_for(day, events,
load_index())`, keep days with at least one feast match (exclude anniversaries — needs a flag or a
split of `_items_for`, which drops the `reason`), stop at N, dedupe pages across days, generalise
`_attach_thumbnails` to a flat list. Cost: D in-memory lookups; DB only on index miss. Caveats:
movable feasts and name links vanish after 2030 (no data file); the mockup's "Tomorrow" label is
relative to `liturgical_date()`.

---

## h. News

- Job: `python manage.py fetch_news` (`news/management/commands/fetch_news.py`), run in production
  by the App Platform SCHEDULED job `fetch-news` (in the live spec; not described in the repo, where
  `news/README.md` only lists options). Sources are `NewsSource` rows seeded in
  `news/migrations/0002_seed_news_sources.py`: Vatican News, CNA, National Catholic Register RSS.
  `feedparser`; dedupe by `guid = entry.id or entry.link` with `update_or_create` (rewrites
  title/excerpt every run); 90-day prune.
- Models (`news/models.py`): `NewsSource` (snippet: name, feed_url, enabled, sort_order,
  last_fetched, last_error), `NewsItem` (source, title, excerpt, link, guid unique, published_at,
  image_url, topic, hidden, fetched_at). Admin: Wagtail snippet viewset (`NewsItemViewSet`).
  `news/tests.py` is empty.
- Rendering: only `sitesofgrace/templates/home/includes/_news_feed.html` (excerpt at l.31,
  autoescaped), from `home_page.html:146–148`. **News renders nowhere else.**
- **The stray "undefined"**: no project code produces it. There's no "undefined" in project JS/templates
  on any news or summary path, Python would print "None", and the only news JS just toggles visibility.
  The local copy (Aug 2026) has **0 of 120** news items and no site/saint/trail/travel text
  containing it, so it arrived after August. Most likely cause: `build_excerpt`
  (`fetch_news.py:36–38`) prefers `entry.content[0].value` (full `content:encoded` HTML) over
  `summary`, and `strip_html` (l.22–23, BeautifulSoup `get_text`) keeps every text node, including
  a publisher's figure caption/credit/alt node whose text is literally "undefined"; the
  200-char truncation puts it at the front. **Unconfirmed.** To confirm in the production console:
  `NewsItem.objects.filter(excerpt__icontains="undefined").values("source__name", "guid")`. Fix
  direction: prefer `summary`, decompose `figure/figcaption/script/style/noscript` before
  `get_text`, drop bare `undefined`/`null` tokens, add tests. Because `update_or_create` rewrites,
  a fixed fetch repairs items still in the feeds.

---

## i. Planner URL

The planner is a Wagtail page, `planner.models.PlanPage` (`planner/models.py:104–210`, template
`planner/templates/planner/plan_page.html`), served at `/plan/` (local DB: `/home/plan/`, live).
No Django URL name; links are hard-coded.

**Preselect: `/plan/?site=<SacredSitePage slug>`** — one site, by slug (`request.GET.get("site")`,
l.147). It resolves to a `DestinationCost` via `_match_destination` (l.193–210: `associated_sites`
M2M, then `city__iexact=locality`, then substring) → `plan_data["selected_id"]`
(json_script `plan-data`, read by `planner/static/planner/js/plan.js:2,107`). No multi-site param.
Existing links: `sacred_site_page.html:44` ("Plan a trip here") and `_plan_your_visit.html:32`
("Estimate the cost of this trip →").

---

## j. Explore

- Explore index: a `home.StandardPage` with slug `explore`, `layout="explore_hub"` (set by data
  migration `home/migrations/0006_explore_hub_and_category_directory_layouts.py`), template
  `sitesofgrace/templates/home/explore_hub_page.html` (`StandardPage.get_template`, l.517–522),
  cards from `_get_hub_cards` (l.555–564; the `saints` page is inserted before Pilgrimage Routes).
- Category listings: StandardPages with `layout="category_directory"` under `/explore/`:
  `marian-apparitions`, `eucharistic-miracles`, `saints-and-tombs`, `holy-lands`,
  `shrines-and-basilicas`, `pilgrimage-routes` (the `saints` page uses `saints_directory`).
  Template `sitesofgrace/templates/home/directory_page.html`, cards from `_get_directory_cards`
  (l.566–599). Sites are filed as **children** of their category page
  (`CATEGORY_PARENT_SLUGS`, `import_catalog.py:22–27`), e.g. `/explore/marian-apparitions/lourdes/`.
- Menu: wagtailmenus 4.0.7, database-driven, no `WAGTAILMENUS_*` settings, nothing seeded in code.
  `base.html:37` `{% main_menu max_levels=2 template="menus/main_menu.html" ... %}`; mobile at l.55;
  footer `{% flat_menu "footer-explore" %}` / `footer-learn` / `footer-about`. `menus/main_menu.html`
  hard-appends **Blog** and **Our Story**. Local DB main menu: Interactive Map (1), Explore (2),
  Plan (3), Learn (3 — same sort_order as Plan), Store (4); all `allow_subnav`. The Explore dropdown's
  children are the six category pages (all `show_in_menus`).
- Breadcrumb on site pages: **none exists.** Building one = walk `page.get_ancestors()` below Home
  (Explore › category page › site).

---

## k. Country values (local copy, Aug 2026)

`catalog_sacredsitepage.country` — 240 sites, all live:

| Country | n | | Country | n |
|---|---|---|---|---|
| Italy | 67 | | Ecuador | 1 |
| United States | 39 | | **France (from Clairvaux)** | 1 |
| France | 19 | | Ireland | 1 |
| Israel | 16 | | **Italy (blood relic)** | 1 |
| Spain | 13 | | **Italy (St. Columban)** | 1 |
| Germany | 8 | | **Italy (tomb)** | 1 |
| Poland | 8 | | Japan | 1 |
| Belgium | 5 | | **Japan (martyrdom)** | 1 |
| India | 5 | | Lebanon | 1 |
| Argentina | 3 | | Nicaragua | 1 |
| Canada | 3 | | Northern Ireland | 1 |
| England | 3 | | Rwanda | 1 |
| Netherlands | 3 | | **Spain (Camino pilgrimage)** | 1 |
| Vatican City | 3 | | Sweden | 1 |
| Venezuela | 3 | | Switzerland | 1 |
| Austria | 2 | | **Switzerland (St. Peter Canisius)** | 1 |
| Colombia | 2 | | Turkey | 1 |
| Czech Republic | 2 | | **Uganda (martyrdom)** | 1 |
| Egypt | 2 | | United Kingdom | 1 |
| Lithuania | 2 | | **USA** | 1 |
| Mexico | 2 | | Bosnia and Herzegovina | 1 |
| Palestinian Territories | 2 | | Brazil | 1 |
| Peru | 2 | | Croatia | 1 |
| Portugal | 2 | | Cyprus | 1 |

Junk/variants: 8 parenthetical qualifiers (bold); `USA` vs `United States`; `England` /
`Northern Ireland` / `United Kingdom` (decide whether to keep constituent countries);
`Palestinian Territories`.

Other country columns: `catalog_pilgrimagetrailpage.country`: `France & Spain` (1), `United States` (1).
`planner_destinationcost.country`: Italy 6, France 3, Ireland 2, Israel 2, Poland 2,
**`Bosnia & Herzegovina`** 1, England 1, Mexico 1, **`Palestine`** 1, Portugal 1, Spain 1,
Switzerland 1 — spelled differently from the site values (`Bosnia and Herzegovina`,
`Palestinian Territories`). Any join by country string will miss these.

---

## l. Pilgrim accounts

- No custom user model (no `AUTH_USER_MODEL`); default `auth.User`. Profile
  `pilgrims.models.PilgrimProfile` (`pilgrims/models.py:42`, OneToOne `related_name="pilgrim"`),
  auto-created by `pilgrims/signals.py:31`.
- django-allauth: email login, mandatory verification, `ACCOUNT_SIGNUP_FORM_CLASS =
  pilgrims.forms.AgeConfirmationSignupForm` (13+), `LOGIN_REDIRECT_URL="/pilgrims/"`; URLs under
  `accounts/`; templates in `sitesofgrace/templates/account/`.
- Templates check `request.user.is_authenticated` everywhere (`base.html:24, 42–47, 54, 56, 147`;
  `includes/_account_menu.html:27`; `home/home_page.html:125`; `home/map_page.html:26`;
  `pilgrims/profile_detail.html:56, 108`; `pilgrims/photo_detail.html:33`;
  `catalog/templates/catalog/sacred_site_page.html:117`; `sacred_site_gallery.html:41`).
  The only template `is_staff` check is `sacred_site_gallery.html:65` (staff hide form).
  Python: `pilgrims/admin_views.py:26–30` (`staff_required`), `pilgrims/permissions.py:174`,
  `pilgrims/wagtail_hooks.py:71`. Context processors include `django.contrib.auth` and `request`;
  no custom user context processor. `v2_enabled(request)` can rely on `request.user.is_staff`.

---

## m. Mockup vs. how the site works

| # | Mockup | Conflict | Proposal |
|---|---|---|---|
| 1 | Map/dot colours: Marian #FFFFFF, Eucharistic **#D96B5F (red)**, Saints **#C79A42 (gold)**, Shrine **#8FB9DD (sky)**, Holy Land **#3E7A5A (green)** | Neither Python `CATEGORY_STYLES` nor the map's JS styles look like this (Eucharistic is gold, Saints navy, Shrine dark blue). Rule 7 says dots come from CATEGORY_STYLES. | **Your call.** Default: v2 maps use the Interactive Map's current JS colours via `sog-maps.js`, so all maps match. Adopting the mockup palette would be a deliberate site-wide recolour, done once in Python + JS. |
| 2 | Site map minZoom 14 / maxZoom 16 with fixed radii; hub map maxZoom 13; river/Umbria polygons with permanent "Gave de Pau"/"Umbria" labels; route polylines | Rule 7: maxZoom 16, `radiusFor` everywhere, no permanent labels. The polygons were stand-ins for missing tiles. | maxZoom 16 on all maps, `radiusFor` on every site dot, no context shapes or permanent labels (the Esri reference layer already labels places). |
| 3 | At a Glance: Address, Time needed, Admission, Accessibility, Active place of worship + schedule link, Church recognition with year | No address, admission, worship/schedule, approval year/authority fields. Website is `location_link`. Time needed ≈ `quick_ideal_stay`; Accessibility = `quick_accessibility`. | Additive nullable fields (`address`, `admission`, `worship_note`, `schedule_url`, `recognition_year`, `recognition_authority`). Reuse `location_link` (label "Official website") and the existing quick_* fields. Rows with no data are hidden. |
| 4 | Badge "Church approved · 1862" | `canonical_status` holds canonical terms (`Nihil obstat`, `Curatur`, legacy `Constat de…`). Under the 2024 DDF norms, *nihil obstat* is not a declaration of supernatural origin, so a blanket "Church approved" label would overstate it. | Show the term with an editorially approved plain-English gloss, mapped value by value (you write the table). Hide "Not Applicable" (ALWAYS-ON candidate). No year unless `recognition_year` is filled. |
| 5 | Breadcrumb "Explore › Marian Apparitions › Lourdes · More in France" | No breadcrumb exists. No destination hubs exist. Countries are dirty (k). | Breadcrumb from `get_ancestors()` (can be ALWAYS ON or v2-gated). "More in …" only when a live hub covers the site, so it waits for the hub phase and country cleanup. |
| 6 | Section bar: Overview, Story, Recognition, Plan Your Visit, Where to Stay & Map, Guided Pilgrimages, Nearby, Prepare, Photos | The current rail has Catholic Teaching, Go Deeper and Location. The mockup drops them, and Rule 4 forbids losing content. The rail is gated at ≥2 entries. | Keep every existing section rendered. Catholic Teaching feeds the readbox's "Catholic teaching" cell (or stays a section). Go Deeper and Location stay as sections. Fix the Plan-position quirk when Catholic Teaching is empty. |
| 7 | Church Recognition readbox (tradition / Church judgment / reported healings / teaching) | One rich field `church_recognition` today. | Optional new rich fields for the four parts. Fall back to the single field when they're empty. |
| 8 | Plan Your Visit badge "Fully researched / Essential visit guide", per-panel "[Needs confirmation]", admin-only review dates | No fields. | `guide_level` choice (blank option), `needs_confirmation` bool on `SiteTravelSection`, admin-only `last_reviewed`. |
| 9 | Quick Card | The mockup folds it into At a Glance. Today it disappears when there are no travel sections. | At a Glance renders independently of travel sections. |
| 10 | Where to Stay: lodging list, walk minutes/miles, slope, step-free, verified route polylines | No lodging model. Computing walk times or routes needs a routing service (Rule 10 forbids third-party geocoders, and a routing API is the same concern). | Lodging model with hand-entered minutes/miles/slope/step_free/verified and an optional hand-drawn route (GeoJSON). Routes only when verified, as the mockup says. No geocoding. |
| 11 | "Check availability" booking CTA; "View on operator site ↗" | Affiliate/partner links. | Rule 9: `rel="sponsored nofollow noopener"` plus the adjacent disclosure; link to an Affiliate Disclosure page only if one is live (none exists today). |
| 12 | Guided pilgrimages (Tour model, many-to-many to sites), "elsewhere in France" fallback, register interest (signed-in, count per site) | New models. The country fallback depends on country cleanup. | New Tour/Operator models with discrete fields. `TourInterest(user, site)` unique, staff-visible count, no email list. Signed-out visitors get a sign-in link (no-JS friendly). |
| 13 | "Plan your pilgrimage" anchors to #s-how; "Add to a trip plan" / "Plan a trip here" are `#` | The real planner takes `/plan/?site=<slug>` (one site). | Point those CTAs at `/plan/?site=<slug>` and keep the anchor button for in-page navigation. |
| 14 | "Save to my journey" / "Mark as visited" | Already exist as `{% journey_buttons page %}` (SiteVisit `want_to_go` / `visited`). | Restyle the existing buttons. No new backend. |
| 15 | Nearby: "about 20 min drive"; "Connected by St. Bernadette" | No drive-time data, and computing it needs a routing service. The saint link is derivable from `associated_saint` / `related_saints`. | Show miles only (existing `nearby_sites`). Add the "Connected by" group from shared saints. Drop drive times. |
| 16 | Prepare spiritually: prayer text, reading checklist, travel.state.gov link | No fields. | Optional fields (`prayer`, `reading_list`). Use the State Dept country page only when a cleaned country code exists, otherwise the generic link. |
| 17 | Sources: primary references; "Report something that's wrong" | No references field and no report form. | `sources` rich field. Report form for signed-in users stored in the DB (no IPs, Rule 10), or a mailto as a first step. |
| 18 | Pilgrim Photos moved to the end | Today it sits before In the Area. | Move it under v2. Existing flow unchanged. |
| 19 | Homepage removes the three-column band and News | Today in the Church, Featured Sites/Saints and the community teaser would disappear for everyone with v2 on. The `fetch-news` job keeps running for nothing. Partners and Support bands aren't shown in the mockup. | Confirm removal (v2 on only; off is unchanged). Keep Partners and the Support band unless you say otherwise. Decide whether to pause `fetch-news` later. |
| 20 | Upcoming feasts (next 4 within 60 days) | Feasible with the existing liturgy code (g). Calendar data ends in 2030. LocMem cache is per process. | `upcoming_feasts()` as sketched. Add a test that warns when the next year's LitCal file is missing. |
| 21 | Destinations band, Explore "By destination", destination hub page (map, lengths of stay, day trips with times, local travel, auto "Go deeper") | No hub model. Day-trip times are hand data. | New `DestinationHubPage` with discrete fields and an M2M to sites, under a `destinations` index. Saints, routes and tours aggregated from member sites. |
| 22 | Nav: no Store; "Plan a Pilgrimage"; Learn dropdown | The live menu (DB) has Store, and Plan and Learn share sort_order 3. Blog and Our Story are hard-appended in the template. | Menu changes are admin edits, not code. Confirm Store's fate. Fix the sort-order tie in the admin. |
| 23 | No-JS: views hidden without JS; text clamped even without JS; dropdowns are buttons only | Rule 8: pages work without JS. | Clamp only under a JS-added class. Dropdown headings stay links. Maps get list alternatives (circleMarkers aren't keyboard-focusable). |
| 24 | Leaflet from cdnjs without SRI; Google Fonts with Cormorant 700 / Lora 600 | The site loads Leaflet from unpkg **with SRI** and already uses Google Fonts (plus Inter). | Keep the site's existing Leaflet tag. Add font weights only if a design element needs them. |
| 25 | Unicode icon glyphs, colour-only category dots, white Marian dot on white | Accessibility. | `aria-hidden` on glyphs, a text label beside every dot, a visible border for Marian dots. |

---

## Decisions (2026-10-21)

0. **Local Django runs in Docker**, not the Windows venv (the Application Control policy is left
   alone). `docker-compose.dev.yml` adds a `web` service built from the production Dockerfile
   (`target: runtime`), repo mounted at `/app`, settings `sitesofgrace.settings.docker_dev`
   (dev settings + `DATABASE_URL` → the existing `db` container). Rules 11 and 12 use it:
   `docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm web python manage.py check`
   / `... test` / `... up web` (runserver 0.0.0.0:8000 → localhost:8000). Production is unchanged.
1. **Category colours: the live Interactive Map's values win.** Python `CATEGORY_STYLES` becomes the
   single source with those fill/stroke values (the `dot` colour stays); the map JS, its legend, the
   nearby chips and every new map read it via `json_script`. No hard-coded copies. ALWAYS ON. The
   mockup's dot colours are ignored.
2. **Status badge.** Hiding "Not Applicable" (and blank) is ALWAYS ON. Plain-English labels, the
   Latin term only in a tooltip/`title`. Mapping, from the values actually stored (local copy, Aug 2026):

   | Stored `canonical_status` | Pages | Label |
   |---|---|---|
   | Constat de supernaturalitate (legacy) | 19 | Church approved · &lt;year&gt; — **no year field exists**, so "Church approved" until one is added |
   | Nihil obstat | 1 | Devotion permitted |
   | Prae oculis habeatur | 0 | Permitted, under observation |
   | Curatur | 0 | Under the bishop's review |
   | Sub mandato | 0 | Under Church supervision |
   | Prohibetur | 0 | Not permitted (the stored choice is "Prohibetur"; the norms' full phrase is "Prohibetur et obstruatur") |
   | Declaratio de non supernaturalitate | 0 | Declared not supernatural |
   | Recognized Devotion | 33 | **No fit — not mapped.** Shown as stored until you decide |
   | Not Applicable | 185 | hidden |
   | blank | 2 | hidden — "No Church judgment yet" has no stored value to map from (e.g. Buenos Aires' text says "PENDING" but the field is blank) |

3. **Homepage (v2 on):** remove the three-column band (Featured Sites and Saints, Your Journey,
   Today in the Church) and News. Partners, the Support band and the Store menu item stay, in their
   current order, after Upcoming feasts.
4. **No computed travel times.** Hand-entered walking data only (walk minutes, slope, step-free,
   optional verified route). Nearby cards show miles only. Hub day-trip times are hand-entered text.
   *(This overrides Phase 1 brief item 9's "about N min drive".)*
5. **Address** field added (Char 200, nullable). The official website reuses `location_link`.
6. **At a Glance** renders on its own, with or without travel sections.
7. **Breadcrumb** (Explore › Category › Site) ships in Phase 1.
8. **Countries:** "USA" → US; "United Kingdom" → GB, displayed "United Kingdom" (applied by Phase 4's
   `propose_country_codes`).
9. **News "undefined":** no further investigation; News leaves the v2 homepage.
10. **The 25 mockup-vs-site items (m):** go with the proposals unless they conflict with the above;
    changes are listed at the Phase 1 STOP.

## Follow-ups (not in scope for v2 batch 1 unless you say so)

1. **Autopush branch guard (do before `.autopush-pause` is ever removed).** `tools/autopush.ps1`
   hard-codes `$Branch = 'main'` but never checks the current branch. Unpaused on
   `pilgrimage-v2`, it would commit everything there, `git pull --rebase origin main` (rebasing the
   branch onto main), then `git push origin main`. Add a guard at the top:
   `if ((git rev-parse --abbrev-ref HEAD) -ne $Branch) { Write-Log 'SKIP' 'not on main'; exit 0 }`.
2. **psycopg blocked by Windows Application Control.** As of 2026-10-21, Django can't load
   psycopg's binary DLL ("An Application Control policy has blocked this file"); it worked on
   2026-10-15. `manage.py check`, tests and runserver will fail until this is resolved (allow-list the
   venv's `psycopg_binary` DLLs, or install a signed libpq). Rule 11 and Rule 12 depend on it.
   The local queries in this document ran through `psql` inside the Docker container instead.
3. **Credentials in `sitesofgrace/settings/local.py`.** It holds what look like live DigitalOcean
   Spaces keys. It's gitignored and was never committed, but under SOC 2 those belong in env vars.
4. Category colours are defined twice with different values (b, m.1). Pick one source of truth.
5. Interactive Map popups concatenate unescaped values (e).
6. `?photos_added=` echoes arbitrary query text in the flash message (c).
7. `has_location_section` treats a 0.0 coordinate as missing (Decimal truthiness).
8. News: fix `build_excerpt` and add tests once the production query confirms the cause (h).
9. LocMem cache: liturgy index invalidation only reaches one worker. Consider a shared cache if
   more workers are added.
10. Stale comments: `catalog/models.py:31–33` path; `PilgrimPhoto` "unused until phase 4" docstring.
11. **Contact form — resolved by main's `f01f83ce` (merged 2026-10-22).** When this was written,
    `home.ContactPage`, the `contact_url` tag and the "Spot an error? Let us know" link were on no
    branch. Main has since added them (`home/templatetags/contact_tags.py`,
    `includes/_correction_link.html`, the `contact` app). The v2 "Report something that's wrong" button
    now uses `{% correction_url page %}` (`?topic=correction&page=<id>`), renders only while a ContactPage
    is live, and replaces the "Spot an error?" link when v2 is on; with v2 off the link shows as on main.
    What's left is a content step in production: publish the ContactPage at /contact/ (the old
    StandardPage there must be renamed and unpublished first, since Wagtail can't change a page's type).
12. **Run `travel_content_report` against production after merge.** The local copy predates the October
    travel import (its 226 sections are mostly the legacy "Additional Information" panel; the closest
    pair scored 0.53, so nothing was flagged). Run it from the DigitalOcean console:
    `python manage.py travel_content_report --out /tmp/travel_report.csv --all && cat /tmp/travel_report.csv`
    (the console has no file download, so copy the printed CSV).
13. **Privacy Policy wording on server logs.** Rule 10 covers what the app stores, and v2 stores no
    visitor IPs (tour clicks are daily counts; interest is user + site). The platform's own request
    logs are separate: gunicorn's access log (`--access-logfile -` in the Dockerfile) and App
    Platform's log retention record the IP of every request, `/go/tour/` included. Leave that logging
    as it is, but check that the Privacy Policy's wording about server logs matches it.
14. **Affiliate Disclosure page before affiliate tours.** A live Affiliate Disclosure page (slug
    `affiliate-disclosure`) must exist in production before any `GuidedPilgrimage` with
    `is_affiliate_link=True` is set live. Tours with ordinary operator links can launch without one;
    affiliate links can't. (The disclosure line links to the page automatically once it's live.)
15. **Test isolation (pre-existing on main).** `manage.py test home pilgrims.tests.test_profile_page` fails
    2 tests on `origin/main` too (`SiteTileImageTests`, `SharedPhotosGridTests`): `home` tests create
    extra Wagtail Sites, the cached site root paths survive into the pilgrims tests, and `page.url`
    there renders absolute (`http://localhost/...`) while the template renders relative. The full suite
    passes because of its order. Fix later by clearing the site-root-paths cache in those tests' setUp
    (or asserting on `page.get_url()` with the request).
16. **`SPACES_PRIVATE_KEY` is stored unencrypted.** In the live App Platform spec it's an app-level
    GENERAL variable with RUN_AND_BUILD_TIME scope, so it's readable in the spec and available at
    build time. **Don't change it during go-live.** After v2 has been "on" for a week, make it an
    encrypted (SECRET), run-time-only variable: read the live spec with `doctl apps spec get`, change
    that one entry, show the masked diff, get an explicit "yes", then `doctl apps update --spec`.
    The change triggers a redeploy, so it must not share a deploy with anything else.
17. **Trip planner `/plan/` scrolls sideways on phones (pre-v2).** `tools/check_overflow.py` found the
    planner form 528 px wide at 360, 390 and 430 px: `.plan-global-fields` is a two-column `1fr 1fr`
    grid whose selects can't shrink, and `.plan-stop` adds a fixed 92 px column plus 42 px of right
    padding (`planner/static/planner/css/plan.css`). Every v2 page passes. Fix it after go-live in its
    own small PR (columns as `minmax(0, 1fr)`, controls `width: 100%`, one column under ~480 px), then
    re-run `tools/check_overflow.py` over the whole sitemap.
18. **GO-LIVE.md: exact filenames for imports, not patterns.** Its import steps use globs such as
    `tools/imports/*site_details*.json`. Since the pilot PR, `tools/imports/` holds each source file
    beside its `_converted.json`, so every pattern matches two files and the importers refuse it
    ("must match exactly one file"). Change the steps to name the exact file (for example
    `tools/imports/site_details_pilot_2026-10_converted.json`), as was done for the pilot import.
