# Trip Planner v2

Everything new ships **behind `SOG_PLANNER_V2`** (`off` by default, `staff`, `on`). It's checked in one
place, `core.v2.planner_v2_enabled(request)` and `{% planner_v2_enabled %}`, and set separately from
`SOG_V2_ENABLED`. With the switch off, `/plan/` is **byte-identical to main**. The test
`planner/tests/test_flag_off.py` compares four renders against copies made on `origin/main`: signed out,
`?site=`, signed in with journey picks, and the rest of v2 on. **Migrations are additive** (0004–0006: new
tables and nullable columns only; 0005 backfills slugs). The live spec has no `SOG_PLANNER_V2`, so
merging changes nothing visible.

## What's in it

1. **Data model (phase 1)**
   - **Destinations:** `DestinationCost` gains a slug (backfilled; `mexico-city`), coordinates, and a
     gateway airport.
   - **Curated plans:** `DestinationPlanDay` holds a destination's curated days, edited inline as
     "Curated plan".
   - **Saved trips:** `Trip` / `TripStop`. Prices are never stored.
   - **Settings and links:** `PlannerSettings` (booking links off, max 6 stops) and the
     `PlannerBookingLink` snippet.
   - **Commands, each with `--dry-run`:** `fill_destination_coords` (`--set slug=lat,lng`),
     `propose_destination_sites`, `apply_destination_sites`, `import_plan_days`.
2. **One itinerary engine (phase 2):** `planner/itinerary.py`, pure Python.
   - **Days:** arrival day first; curated days, then free days. Rows that don't fit are faded with
     "add a night". Without curated days, "Suggested order" uses the destination's sites in
     nearest-neighbor order. Distances are whole miles, never drive times.
   - **Budget:** ported exactly from `plan.js`. Golden test: Rome 4 + Assisi 3, 2 travelers,
     mid-range = **$4,265 / $2,132**.
3. **The page (phase 3):** server-rendered from `?t=…&d=&p=&l=&pace=`, so shared links work without
   JavaScript.
   - **JavaScript:** swaps in the same fragments from `/plan/build/`. Search is `/plan/search/`, a
     keyboard listbox.
   - **Adding places:** `?site=` adds that site's destination first. "Near your route" suggests a
     destination within 150 mi.
   - **Sidebar:** route, budget, legal notice, save / share / print. The group card uses the tours
     None state, never sample tours.
   - **Phones and print:** a sticky total bar on phones; a one-page itinerary in print.
4. **Saved trips (phase 4)**
   - **Saving:** Save to My Pilgrimage (signed out, the button goes to sign-in with the plan kept). My
     Trips appears in the account menu and on the passport page.
   - **Sharing:** links are `/plan/t/<token>/` (read-only, noindex, nothing about the account). Turning a
     link off revokes it; turning it on again issues a new one.
   - **Protection:** owner-only on every write (staff too); CSRF; rate limits per user with no IPs.
     Share URLs always use `https://sitesofgrace.com`.
5. **Booking links (phase 5), built and switched off:** `/go/planner/<id>/` counts clicks (no IP, user
   or cookie) and 302s with `sub_id` = the first stop. Both it and the booking card 404 / stay hidden
   unless Settings › Trip planner › show booking links is on **and** the Affiliate Disclosure is live.
   That's checked on every request, and the admin refuses the setting otherwise.
6. **Content:** `tools/imports/plan_days_2026-11.json` (22 destinations, 55 days, 20 gateways) and
   `tools/imports/destination_sites_proposed_2026-11.csv` (66 approved rows).

## Tests

- **Full suite:** 815 tests. The only failures are the two environment ones that fail on main too
  (Spaces region env var; a stdin prompt test). See `docs/planner/known-flakes.md`.
- **Planner:** 165 tests.
- **Browser checks:** `tools/check_planner.py` (Playwright, 1440 and 390) covers search, Popular,
  reorder, nights, the share link, reload and no-JS. `tools/check_overflow.py` finds no sideways
  scroll at 360/390/430.

## After merge (production, one at a time: dry run → review → run → verify)

1. `fill_destination_coords`
2. `fill_destination_coords --set dublin=53.3498,-6.2603`
3. `apply_destination_sites tools/imports/destination_sites_proposed_2026-11.csv` (no `--skip-missing`)
4. `import_plan_days tools/imports/plan_days_2026-11.json`
5. `SOG_PLANNER_V2` → `staff` for review. It goes to `on` only after the legal pages and the Privacy
   Policy addition (`docs/planner/privacy-addition.md`) are published.

**Rollback:** `SOG_PLANNER_V2` → `off`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
