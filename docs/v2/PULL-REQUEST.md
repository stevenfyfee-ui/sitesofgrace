# Pilgrimage Platform v2, batch 1

Everything new ships **behind `SOG_V2_ENABLED`** (`off` by default, `staff`, `on`), checked in one
place: `core.v2.v2_enabled(request)` and `{% v2_enabled %}`. With the switch off, every page's HTML
is byte-identical to main, except for two always-on fixes. All migrations are additive. Go-live steps:
`docs/v2/GO-LIVE.md`.

## Always on (with the switch off too)

- **"Not Applicable" never renders:** no status badge, chip or row for blank or "Not Applicable".
- **One source for category colors:** `catalog.models.CATEGORY_STYLES` holds the live map's values,
  and the map JS, legend, chips and every new map read it (`{% category_styles_json %}`). No
  hard-coded copies remain.

## Behind the switch

1. **Sacred site page (phase 1)**
   - **Layout:** breadcrumb hero with plain-English status labels (the Latin term in a tooltip), a
     sticky section bar listing only filled sections, an "At a Glance" panel, and an Overview card.
   - **Content:** Read more on The Story and Church Recognition, the "How to read this account" box,
     and Plan Your Visit guide and needs-confirmation pills.
   - **Further sections:** Nearby cards (miles only) with "Connected by <saint>", Prepare spiritually,
     Information & sources, and Pilgrim Photos last.
   - **Report button:** "Report something that's wrong" uses main's `correction_url` and replaces
     "Spot an error?".
2. **Guided pilgrimages (phase 2, new `tours` app)**
   - **Admin:** operator and tour snippets with stops and departures.
   - **Site page:** "Guided pilgrimages that include <site>"; when there are none, the "Prefer to travel
     with a group?" card, up to two tours elsewhere in the same hub or country, and a POST-only
     "I'm interested" button.
   - **Interest:** signed-out clicks register on sign-in within 30 minutes, via the session.
   - **Outbound links:** `/go/tour/<id>/` counts clicks per day with no IP, user or cookie. Affiliate
     links get `rel="sponsored nofollow noopener"`, with the `tour_links` notice beside them.
3. **Where to Stay & Map (phase 3)**
   - **Data:** map points and lodging per site, with validated coordinates and GeoJSON walking routes.
   - **Map:** a Leaflet map on the new shared `static/js/sog-maps.js` (self-hosted Leaflet), with layer
     toggles and numbered lodging markers. Routes are drawn only when verified.
   - **Without JavaScript:** a server-rendered list.
   - **Outbound links:** `/go/lodging/<id>/` counts clicks; the `travel_links` notice sits beside them.
4. **Destinations (phase 4, new `destinations` app)**
   - **Country codes:** `country_code` plus `propose_country_codes`, which proposes, then applies only
     approved rows.
   - **Hub pages:** a Destinations index and hub pages (curated plus auto-included sites, full-width
     map, lengths of stay, major sites, day trips, local travel, and Go deeper with saints, routes and
     tours).
   - **Links into hubs, live hubs only:** the Explore dropdown "By destination" group, "More in <hub>",
     "Visit in <hub>" on saint pages, and the hub's travel advisory.
5. **Homepage (phase 5)**
   - **Unchanged:** the hero and four image cards stay as they are.
   - **New:** "Explore by destination" tiles and "Upcoming feasts" (next 4 in 60 days, from the liturgy
     data and cache).
   - **Hidden in the template only:** the three-column band (with Today in the Church) and News. All
     their fields, the liturgy app and the fetch-news job stay.

## Commands (all follow `docs/v2/IMPORT-RULES.md`)

- **Imports:**
  - `import_site_details`, `import_site_map` and `import_hubs` all support `--dry-run` and `--verify`.
  - Rows match on ID plus title, and blank means no change.
  - A filled field is never overwritten, pages with drafts are skipped, and a second run reports 0.
- **Read-only reports, `--out -` prints to the console:** `travel_content_report`,
  `eucharistic_kind_worksheet` and `propose_country_codes`. `propose_country_codes` also has
  `--apply` for approved rows.
- **Setup:**
  - `create_destination_hubs` creates the index and four hubs as unpublished, title-only drafts.
  - `v2_dev_sample` loads local sample data only; it refuses to run unless DEBUG is on and the
    database is local.

## Also on the branch

- **Merge of main:** `44d90387` (legal pages, notices, self-hosted Leaflet, log format) and `f01f83ce`
  (Contact page). Conflicts are resolved as described in the merge commit.
- **Local development in Docker:** `Dockerfile.dev`, `docker-compose.dev.yml` and
  `settings/docker_dev.py`. Dev only; production's Dockerfile is unchanged.
- **Docs:** `docs/v2/` holds the standing rules, phase 0 findings and decisions, import rules, this
  summary and the go-live runbook, plus the mockup in `docs/mockups/`.

## Testing

- **Suite:** 629 tests pass in the dev container (Rule 11: `check`, `makemigrations --check`, phase
  apps, full suite).
- **Switch off:** diffed byte for byte against main's HTML on 20+ pages.
- **Screenshots:** each phase at 1440 and 390, with the switch on and off.
- **Known issue (pre-existing on main):** `test home pilgrims.tests.test_profile_page` run together
  fails 2 tests, a stale Wagtail site cache (follow-up 15). The full suite passes.

## Follow-ups (`docs/v2/phase0-findings.md`)

- An autopush branch guard before `.autopush-pause` is ever removed.
- Run `travel_content_report` on production after merge.
- Check the Privacy Policy wording on server logs.
- The Affiliate Disclosure page must be live before any affiliate tour or lodging.
- The home/pilgrims test isolation.
- Moving the three pre-v2 maps onto `sog-maps.js`.
