# Future Saints Phase 1: owner review

**Status:** on `main` since PR #14 (merged 2026-11-06 05:49 UTC) and deployed (deployment `e52d5a60`),
**dormant**: `SOG_FUTURE_SAINTS` is not set in production, so the switch is off. Not yet reviewed by the
owner. This document is that review.

## How it reached main without review

Two Claude Code sessions were working in the same checkout (`C:\Users\steve\sitesofgrace`). At 21:10
the other session switched that checkout from `future-saints` to a new `fix/mobile-menu` branch. At 21:25
the Future Saints session committed (`9e5733bf`) without re-checking the branch, so the commit landed
on `fix/mobile-menu`. The mobile-menu fix (`40cb7e88`) was committed on top, and PR #14 merged both.
`main` auto-deploys. The standing rules now require one worktree per session, a branch check before
every commit and push, and a commit list check before every merge (`docs/v2/STANDING-RULES.md`, rules
13–15).

## Proof it is dormant in production (2026-11-05, read-only)

| check | result |
|---|---|
| Live app spec (`doctl apps spec get`) | `SOG_FUTURE_SAINTS` absent. (For reference: `SOG_V2_ENABLED` and `SOG_PLANNER_V2` are "on"; not changed by this work.) |
| `/future-saints/`, `/future-saints/saints/`, signed out | 404, 404 |
| `/`, `/learn/saints/st-francis-of-assisi/`, `/explore/marian-apparitions/lourdes/`, `/interactive-map/`, `/plan/`, signed out | all 200; none contains `future-saints`, `Future Saints`, `future-saints.css`, `Future Saints Serif`, `fs-serif` or any `@font-face`. (Their only Lora reference is the adult site's existing Google Fonts link, unchanged.) |
| `/sitemap.xml` | 494 URLs, none under `/future-saints/` |
| `showmigrations future_saints` | `[X] 0001_initial`, `[X] 0002_church_status_note` (two new, empty tables) |
| Future Saints pages in production | 0 of either type; no page with `future-saints` in its path; no "Future Saints reviewers" group; no workflow assignment. `create_future_saints_tree` has never been run there. |

Local render diff, switch off (same local database, CSRF token normalized):

| page | `5378fd61` (before) vs `9e5733bf` (Future Saints only) | `9e5733bf` vs `1b0f9e0e` (current main) |
|---|---|---|
| `/` | identical (31,644 bytes) | 86 changed lines, all from the mobile-menu fix: collapsible Explore/Learn sections in the mobile menu and the new menu script in `base.html` |
| `/learn/saints/st-francis-of-assisi/` | identical (14,991 bytes) | the same 86 lines, same source |

**Shared template.** Both changes edit `sitesofgrace/templates/menus/mobile_menu.html`: the mobile-menu fix
rewrites the loop over menu items (collapsible sections); Future Saints appends one gated `<li>` after the
loop, on the same line as the last `{% endif %}` so it adds no bytes when off. With the switch **on**
(locally only), both work together:
- `tools/check_mobile_menu.py` (the mobile-menu fix's own check): all checks passed on iPhone 13 and
  Android 360×640, keyboard, resize and 1440; it swiped to "Future Saints" as the menu's last row and
  found it on screen and tappable.
- A joint check: the mobile menu lists exactly one Future Saints link, as the last row; sections still
  toggle; tapping the link opens `/future-saints/`; the desktop menu shows the item.

## What `9e5733bf` contains (60 files, all new except three)

Changed (additive only):
- `sitesofgrace/settings/base.py`: `"future_saints"` in INSTALLED_APPS; `SOG_FUTURE_SAINTS` (default "off")
- `sitesofgrace/templates/menus/main_menu.html`, `menus/mobile_menu.html`: the gated "Future Saints" item

App `future_saints/`:
- `switch.py`: `future_saints_mode()`, `future_saints_enabled(request)`, `future_saints_public()`
- `models.py`: `FutureSaintsHomePage`, `FutureSaintsIndexPage`, the gate mixin (404 / noindex /
  private cache / sitemap exclusion)
- `migrations/0001_initial.py`, `0002_church_status_note.py`
- `templatetags/future_saints_tags.py`: `{% future_saints_enabled %}`, `{% future_saints_menu_url %}`
- `management/commands/create_future_saints_tree.py`, `future_saints_dev_sample.py`
- `tests/`: `base.py`, `test_switch.py`, `test_pages.py`, `test_privacy.py`, `test_adult_unchanged.py`,
  `test_commands.py`

Templates `sitesofgrace/templates/future_saints/`: `base.html`, `future_saints_home_page.html`,
`future_saints_index_page.html`, and `includes/` `_header`, `_footer`, `_breadcrumb`, `_subject_card`,
`_feature_card`, `_art_frame`, `_reading_level`, `_section_heading`, `_parchment_panel`, `_icon`.

Static: `sitesofgrace/static/css/future-saints.css`, `static/js/future-saints.js`,
`static/fonts/future-saints/` (four woff2 faces, `OFL.txt`, `README.md`).

Tools: `tools/future_saints_screens.py` (Playwright QA + screenshots).

Docs: `docs/future-saints/future-saints-architecture.md`, `future-saints-content-audit.md`,
`future-saints-affiliate-privacy-gates.md`, `art-manifest.md`, and the eleven screenshots below.

## Real vs. placeholder

| real | placeholder |
|---|---|
| Switch and gating: 404 when off; staff-only in "staff"; noindex, private cache, out of sitemap and search until "on" | All 12 illustration slots show the placeholder art frame (see `art-manifest.md`); a picture renders only with a credit |
| Header (real `SiteSettings.logo` at 2x on an ivory plate; "Future Saints" live text on a gold brushstroke), section nav with a ≤900px disclosure, breadcrumb, footer | No SVG wordmark yet |
| Homepage layout per comp 01: hero, four subject cards in one row at ≥1024, full-width Holy Land card, Choose Your Adventure, Saint of the Week | Card lines, index intros and the Saint of the Week line are "(sample)" text, local only |
| Reading-level control: two buttons with `aria-pressed`, `?level=` + sessionStorage, no cookie, works without JS | It changes no content yet; stories arrive in Phase 2 |
| Five subject indexes with accent band, intro and banner frame | Index grids are empty; staff see "Stories are on the way!" |
| "A note for grown-ups" link logic (live Privacy Policy only) | Privacy Policy is a draft in production, so visitors see no link and staff see a warning chip |
| Church-status footer line (editable field, existing approved wording) | World Discovery Map and Take a Quiz: staff-only "Phase 4" placeholders; Map nav item is staff-only "coming soon" |
| Self-hosted serif (Lora subset, renamed "Future Saints Serif" under the OFL Reserved Font Name clause) | |

Saint of the Week shows the placeholder frame: St. Francis of Assisi has no portrait, and St. Carlo Acutis's
portrait has no `portrait_credit` (production audit).

## Test results

- `future_saints` app: **38/38 pass**.
- Full suite at `9e5733bf`, in a clean worktree on its own test database: 859 tests, **858 pass**, 1 error.
  - The error is `home.tests_v2_golive.LegalCommandsTests.test_set_legal_details_refuses_without_a_prompt`,
    which errors identically on `5378fd61` (it expects no prompt without a TTY, but the command still
    prompts in a non-interactive shell). Pre-existing.
  - Two `home.tests.HomeTests` tests fail in the full run **only because of test order**: they add a
    second default Site, and with two defaults a request for an unknown host picks one in no fixed row
    order. Adding the Future Saints tests shifted the order. A three-line fix (keep one default site, as
    the contact tests already do) is on branch `fix/hometests-single-default-site` (`4a77452d`, not
    pushed); with it the full suite is 858/859 with only the pre-existing error. **Main currently has
    this order-dependent failure.**
- `makemigrations --check`: no changes. `manage.py check`: no errors (26 warnings, all treebeard
  manager / wagtailmenus panel notices from installed packages).
- Browser QA (`tools/future_saints_screens.py`, switch on, local): **38/38 checks pass**, covering:
  - the four cards in one row at 1440 and 1024, 2×2 at 768, one column at 390 and 360
  - the Holy Land card full width below them
  - no third-party requests and no cookies
  - the menu disclosure: keyboard, Esc, focus return
  - the reading level: keyboard, `aria-pressed`, `?level=`, sessionStorage, no cookie, survives a
    reload, works without JS
  - staff-only placeholders
- `tools/check_overflow.py` at 360/390/430 on `/future-saints/` and `/future-saints/saints/`: 0 pages
  with sideways scroll.

## Screenshots (`docs/future-saints/screenshots/phase1/`, device scale factor 2, local, sample data)

| file | what |
|---|---|
| [home-1440.png](screenshots/phase1/home-1440.png) | homepage, 1440, signed out |
| [home-1024.png](screenshots/phase1/home-1024.png) | homepage, 1024 |
| [home-768.png](screenshots/phase1/home-768.png) | homepage, 768 (cards 2×2) |
| [home-390.png](screenshots/phase1/home-390.png) | homepage, 390 |
| [home-360.png](screenshots/phase1/home-360.png) | homepage, 360 |
| [home-390-menu-open.png](screenshots/phase1/home-390-menu-open.png) | 390, section menu opened from the keyboard |
| [home-1440-staff.png](screenshots/phase1/home-1440-staff.png) | homepage, 1440, staff view (slot labels, Phase 4 placeholders, Map "coming soon", privacy chip) |
| [saints-index-1440.png](screenshots/phase1/saints-index-1440.png) | Saints index, 1440 |
| [saints-index-390.png](screenshots/phase1/saints-index-390.png) | Saints index, 390 |
| [saints-index-1440-staff.png](screenshots/phase1/saints-index-1440-staff.png) | Saints index, staff view ("Stories are on the way!") |
| [home-1440-vs-comp01.png](screenshots/phase1/home-1440-vs-comp01.png) | first screen at 1440 beside comp 01. **Contains comp 01's pixels** for comparison; the comps themselves are not committed. |

## Open items for the owner

1. Approve or request changes to the Phase 1 design and the Holy Land placement (brief §10 gate).
2. Whether `fix/hometests-single-default-site` should be pushed as its own PR now (it fixes the
   order-dependent `HomeTests` failure on main).
3. `SOG_FUTURE_SAINTS` stays unset until you decide; "staff" is the next step after this review.
4. Content and legal items from the audit docs: the Privacy Policy (draft) and a children's-section
   note for grown-ups (counsel); illustration commissions and credits; the Amazon gate stays closed.
5. `future-saints-architecture.md` still says Phase 1 was "built on the `future-saints` branch"; it
   is on `main` via PR #14.
