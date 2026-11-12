# Future Saints: open follow-ups

Logged 2026-11-12, at the close of Phase 3. Remove an item when it's done, and note the PR that closed it.

## 1. Importer report wording on real runs

`import_mission_content` (`future_saints/management/commands/import_mission_content.py`, in the
`report()` method) prints "would create" for a new page on **real** runs as well as dry runs.
- Seen on the production import of 2026-11-12: "guide: …/projects/ (new, unpublished): would create".
  The page itself (#2530) was created correctly.
- **Fix in the next Future Saints PR:** say "created" (or "will be created") on a real run and
  "would create" only with `--dry-run`. Add a test that checks both wordings.

## 2. Mission Dolores founding date

The founding date of Mission San Francisco de Asís (Mission Dolores), Founding #6, is unverified.
Is it the founding (June 29, 1776, in many sources) or the formal dedication (October 9, 1776)?
- **Now:**
  - Adult page **#1315** says "Founded October 9, 1776".
  - Hub entry **#6** on the California Missions index (#2523) shows the year only, "1776".
  - That entry is marked **needs-review**, with the note "Founding vs. dedication date unverified
    (June 29 vs. October 9, 1776)".
  - `seed_mission_hub` leaves a needs-review entry exactly as it is.
- **To do:**
  1. Verify the founding date against a primary source (not a secondary summary), and record the
     source.
  2. Fix adult page **#1315**'s `date_display` to match, citing that source. This is an adult catalog
     change, so it follows the usual editorial process.
  3. On hub entry **#6**:
     - set `founded_display` to the verified date;
     - clear **needs-review**;
     - clear (or update) the review note.

     Do this in the admin, or by re-running `seed_mission_hub`, which picks up #1315's corrected
     text only once the entry is no longer needs-review.
  4. Check the hub panel's "Founded:" line for #6 in preview before publishing #2523.
- Related: #7 San Juan Capistrano is also year-only ("1776") on its adult page #1218. It isn't
  marked needs-review, and it stays as it is unless a full date is sourced.
