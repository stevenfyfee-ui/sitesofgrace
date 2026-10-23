# Pilgrimage Platform v2 — going live

The exact production steps, in order. Everything in v2 ships **switched off**: the branch can be
merged and deployed with `SOG_V2_ENABLED` unset and the public site looks exactly as it does today,
apart from the two always-on fixes (category colors read from one place; no "Not Applicable" badges).

Where a step says **console**, it means the DigitalOcean App Platform console for the web component
(Apps → sitesofgrace → Console). The console can't upload or download files, so:

- **Out:** every report command takes `--out -` and prints its CSV to the console. The one-line
  summary goes to stderr, so what you copy is just the CSV. Paste it into a file on your laptop.
- **In:** files you've reviewed (the approved country CSV, the import JSON files) come back
  **through git**. Commit them under `tools/`, merge to main, let the deploy finish, then run the
  command against `tools/...` in the console. Run **`--dry-run` before every real run**, and
  `--verify` after.

---

## 0. Before merging

1. **Back up the database.** In DigitalOcean, open the database used by the app and take a manual
   backup (or, if the plan only has automatic daily backups, note the most recent one's timestamp
   and confirm point-in-time restore is available). **Write down its name / timestamp here:**
   `______________________`
2. In Apps → sitesofgrace → Settings → App-level and component environment variables, confirm
   **`SOG_V2_ENABLED` is not set** (or is `off`).
3. Confirm `AUTOPUSH-BLOCKED.txt` isn't present and `.autopush-pause` is still in place on the laptop.

## 1. Merge and deploy (switch off)

1. Merge the `pilgrimage-v2` pull request into main. App Platform builds and runs the PRE_DEPLOY
   `migrate` job. The new migrations are all additive:
   `catalog 0008–0010`, `tours 0001`, `destinations 0001`, `home 0018`.
2. Wait for the deployment to show **Active**.
3. Spot-check the public site: homepage, a site page, the Interactive Map, Explore. They should look
   as before. The only visible changes are the category colors and the missing "Not Applicable"
   badges.

## 2. Console: create drafts and pull the reports

Run each in the console, then copy what it prints:

```
python manage.py create_destination_hubs
python manage.py propose_country_codes --out -
python manage.py travel_content_report --out - --all
python manage.py eucharistic_kind_worksheet --out -
```

- `create_destination_hubs` creates the Destinations index and four hubs (Rome & Vatican City,
  Assisi & Umbria, Paris & Northern France, Portugal) as **unpublished drafts, titles only**.
  Running it again changes nothing.
- **Country codes:** save the CSV as `tools/country_codes_approved.csv`. Check each proposed code,
  fix any that are wrong, and put `yes` in the `approved` column for the rows you accept. Blank
  codes are the ones the command wasn't sure about. Decide them or leave them unapproved.
- **Travel content report:** your rewrite worklist for near-identical Plan Your Visit text. It changes
  nothing; rewrite in the admin.
- **Eucharistic worksheet:** classify each page's `eucharistic_kind` into the site-details import
  file (step 5b).

## 3. Content steps that aren't v2 but affect it

**Contact page** (the "Report something that's wrong" button stays hidden until this is live):

```
python manage.py swap_contact_page --dry-run
python manage.py swap_contact_page
```

It unpublishes the existing `/contact/` StandardPage, changes its slug to `contact-old`, then creates
a **Contact page** at `/contact/` with its defaults and publishes it. With a live ContactPage
already there, it does nothing. Then edit the Contact page's text in the admin if needed, and check
that `/contact/?topic=correction&page=<any site id>` opens the form with "Submit a correction".

**Legal pages:**

1. If they don't exist yet: console `python manage.py create_legal_pages` (creates ten drafts).
2. Fill in **Settings → Legal details** at the console prompt (the values are typed, never passed as
   arguments, and never echoed back). The pages use seven values: operator name, contact email,
   mailing address, and the four DMCA agent fields. Enter keeps a value.

   ```
   python manage.py set_legal_details
   ```
3. Review the ten drafts in the admin, then **publish all ten together** (or none, if any value
   they use is still blank):

   ```
   python manage.py publish_legal_pages --dry-run
   python manage.py publish_legal_pages
   ```
4. **The Affiliate Disclosure page must be live before any tour or lodging with an affiliate link
   is set live.** Tours and lodging with ordinary links can go live without it; affiliate ones can't.

## 4. First content round-trip through git

Commit the reviewed files to the repo under `tools/` and get them into main the usual way (branch,
pull request, merge). Wait for **Active**. Then, in the console, in this order:

### 4a. Country codes (hubs match sites on them)

```
python manage.py propose_country_codes --apply tools/country_codes_approved.csv --dry-run
python manage.py propose_country_codes --apply tools/country_codes_approved.csv
```

Only rows marked approved are applied. Pages with drafts are skipped and reported, a code that's
already set differently is a conflict, and the `country` text is never changed. Rerunning reports 0
changed.

## 5. Content imports, in dependency order

Each follows `docs/v2/IMPORT-RULES.md`:
- **Matching:** rows match on page ID plus title, and only `"status": "Ready to import"` rows are used.
- **Blank or filled:** a blank value changes nothing, and a field that's already filled with
  something else is a conflict that skips the page.
- **Skipped pages:** pages with drafts are skipped.
- **Reruns:** a second run reports 0 changed.

Prepare the JSON files on the laptop, commit them under `tools/`, merge, wait for **Active**, then:

**5a. Site details**: At a Glance, the "How to read this account" box, eucharistic_kind, guide_level,
prep fields, primary references, recognition_year.

```
python manage.py import_site_details tools/*site_details*.json --dry-run
python manage.py import_site_details tools/*site_details*.json
python manage.py import_site_details tools/*site_details*.json --verify
```

**5b. Map & lodging**: entrances, sacred places, transit, places to stay
(format: `tools/site_map_example.json`). Lodging with `is_affiliate_link: true` only after the
Affiliate Disclosure page is live.

```
python manage.py import_site_map tools/*site_map_*.json --dry-run
python manage.py import_site_map tools/*site_map_*.json
python manage.py import_site_map tools/*site_map_*.json --verify
```

(Keep `site_map_example.json` out of the pattern, or name real files `site_map_2026-11.json` and
use `tools/site_map_2026*.json`. The pattern must match exactly one file.)

**5c. Guided pilgrimages**: in the admin (Snippets → Guided pilgrimages): operators first, then
tours with their stops and departures. Set `is_live` only when a tour is checked. **No tour with
`is_affiliate_link` goes live before the Affiliate Disclosure page.**

**5d. Destination hubs**: text, sites, stay options, day trips, trails. This comes after 4a, because a
hub's automatic site list matches on country codes.

```
python manage.py import_hubs tools/*hubs*.json --dry-run
python manage.py import_hubs tools/*hubs*.json
python manage.py import_hubs tools/*hubs*.json --verify
```

The hubs are still unpublished, so the importer saves a new **draft revision**. Nothing goes public.

**5e. Homepage**: in the admin, Home → "Explore by destination (v2 homepage)" to choose tile order
(optional; otherwise by title) and "Upcoming feasts (v2 homepage)" for the heading.

## 6. Publish the hubs

1. Preview each hub draft in the admin, at desktop and phone width.
2. Publish the hubs that have text (and the Destinations index with the first one). Hubs without an
   intro are skipped and listed:

   ```
   python manage.py publish_hubs --dry-run
   python manage.py publish_hubs                 # or: --slug assisi-umbria --slug portugal
   ```

   Only live hubs appear in the Explore dropdown, the homepage tiles, "More in…" and "Visit in…".

## 7. Switch on for staff

1. App Platform → sitesofgrace → web component → Environment variables: set
   **`SOG_V2_ENABLED=staff`** and save. The app redeploys.
2. Signed in as staff, the site shows v2; everyone else still sees today's site.

### Staff review checklist

- [ ] **Lourdes**: hero badges and "Church approved · <year>", At a Glance, Read more on The Story
      (opens and closes), the account box, Plan Your Visit pills, Where to Stay & Map (select a place to
      stay, toggle the transit layer), Guided Pilgrimages, Nearby, Pilgrim Photos last.
- [ ] **Medjugorje**: the "Devotion permitted" badge (Nihil obstat) and its tooltip.
- [ ] **Assisi pages**: the Basilica of St. Francis shows "More in Assisi & Umbria" and the hub's
      travel advisory in Trip readiness.
- [ ] **The Assisi & Umbria hub at phone width**: the map at the top (about 340px tall), the legend
      underneath, no sideways scrolling, every empty section hidden.
- [ ] **The homepage**: hero and the four image cards unchanged; then Explore by destination,
      Upcoming feasts, Partners, Support band; no three-column band and no News.
- [ ] **A site with no tours**: no Guided Pilgrimages item in the section bar, one wide "Plan your own
      visit" card, the "Prefer to travel with a group?" card, and "elsewhere in <hub or country>".
- [ ] **"Report something that's wrong"** (once the Contact page is live): opens the Contact form set
      to a correction for that page; the old "Spot an error?" link isn't shown as well.
- [ ] **The interest button signed out**: sends you to sign in; after signing in you're back on the
      page and it reads "You've told us you're interested".
- [ ] **The interest button signed in**: registers once; clicking again doesn't add a second count
      (Reports → Group trip interest).
- [ ] **Reports → Outbound clicks**: a test click on "View on operator site" / "Check availability"
      shows up under Tours / Lodging.
- [ ] **Explore dropdown**: "By destination" lists only published hubs plus "All destinations".

## 8. Switch on for everyone

App Platform → web component → Environment variables: set **`SOG_V2_ENABLED=on`** and save. After
the redeploy, repeat a short version of the checklist signed out.

---

## Turning it off

Set **`SOG_V2_ENABLED=off`** (or delete the variable) and save. App Platform redeploys, and every
page goes back to today's layout. Nothing needs to be migrated back.

What stays anyway:

- **The two always-on fixes:** category colors come from one place (the map's colors), and no badge,
  chip or row says "Not Applicable".
- **The new database tables and fields** (site-page fields, map points, lodging, tours, interest,
  click counts, destinations, homepage tiles). They do no harm with the switch off: nothing renders
  them, and `/go/…` and `/tours/interest/` return 404.
- **Draft and published hub pages** still exist. With the switch off nothing links to them, but a
  published hub's own URL still opens. Unpublish the hubs too if they should disappear completely.

## News

Leave the scheduled `fetch-news` job running for now; with v2 on, the homepage simply doesn't show
News. Once v2 has been **on for a few weeks with no rollback**:

1. In App Platform, remove the `fetch-news` scheduled job component.
2. In the admin, Home → News feed: untick **"News feed: enabled"**, so the section stays hidden even
   if v2 is ever switched off.

Nothing else reads the news data. The old items stay in the database (the job did the 90-day
pruning) and can be deleted later from Snippets → News items.
