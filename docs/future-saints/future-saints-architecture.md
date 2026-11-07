# Future Saints: architecture (Phase 0 proposal, Phase 1 as built)

Status: Phase 0 approved by the owner on 2026-11-05 with the decisions below; Phase 1 built on the
`future-saints` branch. Spec: `Sites_of_Grace_Future_Saints_Claude_Code_Build_Brief_v2.md` and the three
comps in `docs/future-saints/` (kept local, not committed).

## 0. Phase 1 as built: owner decisions and differences from the proposal

- **Fonts.** Lora 400, 400 italic, 700, 700 italic from the official upstream (cyrealtype/Lora-Cyrillic
  static TTFs), subset to Latin, Latin-1 and Latin Extended-A plus general punctuation, as woff2 with
  `font-display: swap`. Lora's OFL reserves the name "Lora", and a subset is a Modified Version, so the
  files are renamed **"Future Saints Serif"** (`sitesofgrace/static/fonts/future-saints/`, with OFL.txt
  and a README recording the source). fontTools/brotli were local tools only. Lora has no "←" glyph;
  the back link uses an inline SVG chevron.
- **Accents.** Approved. Saints sage, Mary blue, Eucharistic gold, Missions terracotta, Holy Land sand.
  `--fs-accent-lavender` is used for one thing only: Quiz / "Test Your Knowledge" cards. All are
  `:root` tokens.
- **Logo.** `SiteSettings.logo` PNG at 2x pixel density (a `max-320x88` rendition shown at half size),
  never traced or re-lettered. Its dark lettering is unreadable on the navy bar, so it sits on an
  ivory plate; the artwork is unchanged. "Future Saints" is live text in the 700 weight on a gold
  brushstroke shape.
- **Footer.** The Church-status line is an editable field, `FutureSaintsHomePage.church_status_note`
  (migration 0002), defaulting to the existing approved sentence from the adult footer notice: "Church
  status information should be checked against official sources." The full adult notice isn't reused:
  its "not affiliated with…" wording trips the required no-"affiliate" check, and approved legal text
  isn't edited for this.
- **Editable children's text.** Besides the brief's fields, the "Choose Your Adventure!" heading, its
  intro line and the "Saint of the Week" heading are fields with defaults. Section-nav labels (Saints,
  Mary, Miracles, Holy Land, Missions) and staff-only notes are UI chrome in code.
- **Pictures.** Every illustration slot has an image, alt text and a **credit** field; a picture
  renders only when image and credit are both filled. Saint of the Week uses the SaintPage portrait
  only when `portrait_credit` is filled; otherwise the placeholder frame. No fallback to an uncredited
  canonical image.
- **Reading level: superseded in Phase 2a.** Phase 1 shipped an Explorer/Researcher control
  (`?level=` plus sessionStorage). **Owner decision (Phase 2a review): one version of all text for
  grades 2–5, with no grade labels anywhere on the site, print sheet or metadata.** This replaces brief §1.6
  and the §4 reading-level sections. The control, its JavaScript and its storage are removed; Future
  Saints now uses no browser storage at all. The homepage "Choose Your Adventure" block is gone and
  Saint of the Week takes its place. Its two homepage fields (`adventure_heading`,
  `adventure_text`) are no longer used or shown in the admin, but their columns stay: migration
  0001 is applied in production, and removing fields needs explicit approval (standing rule 4).
- **Links between pages** are set by object or slug lookup (`create_future_saints_tree`, the dev
  sample), never by page ID.
- **Review.** Wagtail moderation workflow, approved. The tree command creates the group "Future Saints
  reviewers" (no members; add, edit and publish only within /future-saints/) and the workflow "Future
  Saints editorial review" on the subtree.
- **Rollback note.** If this code is ever reverted after the Future Saints pages are published, those
  pages would be served by Wagtail without the gate. **Unpublish the Future Saints tree before any
  revert.**

### Phase 3 note: mission companions (not built yet)

Phase 3 adds structured `founding_number`, `founding_date` (with a display text) and a source note to
the Future Saints **mission companion** page. The adult SacredSitePages are not changed. The Mission
Trail's stop order is geographic (south → north) and is **never** used as founding order. Companions
link to the current trail pages, never the duplicates 1144 and 1126 (see the content audit).

Stack, as audited: Django 6.0.7, Wagtail 7.4.2, wagtailmenus 4.0.7, Postgres, `manage.py test`
(Django runner), Playwright 1.64.1 for the tools/ checks.

## 1. Switch

`settings.SOG_FUTURE_SAINTS`, read in `sitesofgrace/settings/base.py` the same way as
`SOG_V2_ENABLED` (base.py:263):

```python
SOG_FUTURE_SAINTS = os.environ.get("SOG_FUTURE_SAINTS", "off").strip().lower()
```

`future_saints/switch.py` matches `core/v2.py` exactly, reusing its `_mode` / `_enabled` so the
three modes behave identically everywhere (unknown value = "off"; "staff" = authenticated
`is_staff`):

```python
def future_saints_mode(): return _mode("SOG_FUTURE_SAINTS")
def future_saints_enabled(request): return _enabled(future_saints_mode(), request)
```

Template tag `future_saints_tags.future_saints_enabled` is a `simple_tag(takes_context=True)`,
used as `{% future_saints_enabled as fs %}`, matching `v2_tags`.

## 2. Page tree and URLs

```
HomePage (/)
└── FutureSaintsHomePage            /future-saints/                (max_count 1)
    ├── FutureSaintsIndexPage       /future-saints/saints/               content_kind=saint
    ├── FutureSaintsIndexPage       /future-saints/marian-apparitions/   content_kind=marian_apparition
    ├── FutureSaintsIndexPage       /future-saints/eucharistic-miracles/ content_kind=eucharistic_miracle
    ├── FutureSaintsIndexPage       /future-saints/holy-land/            content_kind=holy_land
    └── FutureSaintsIndexPage       /future-saints/california-missions/  content_kind=california_mission
```

No collision: there's no `future-saints` or `kids` slug, redirect or URL pattern in code, fixtures,
the local DB, or production (all checked). Fixed Django routes (`sitesofgrace/urls.py`) don't use
the prefix.

**HomePage.subpage_types is not changed.** It doesn't list the new type, so editors can't add a
second Future Saints home in the admin. `create_future_saints_tree` adds the single instance
programmatically (the same way `create_legal_pages` adds LegalPages, which also aren't in that
list). `FutureSaintsHomePage.parent_page_types = ["home.HomePage"]`, `max_count = 1`.

Phase 4's `/future-saints/map/` is a RoutablePageMixin route on FutureSaintsHomePage, so no new
page type and no slug to collide with. `/future-saints/california-missions/projects/` (Phase 3)
is a route on the missions index.

## 3. Models

All in a new app `future_saints`. Additive migrations only, no changes to any catalog/home model.

### Phase 1

**FutureSaintsHomePage(FutureSaintsGateMixin, Page)**, with discrete fields and defaults from the brief:

| field | type | default |
|---|---|---|
| eyebrow | CharField 80 | "Sites of Grace \| Future Saints" |
| headline | CharField 120 | "Explore the Wonders of Our Faith!" |
| subheading | CharField 200 | "Amazing stories, holy people, and places to discover." |
| cta_label | CharField 40 | "Start Exploring" |
| hero_illustration / _alt | FK Image, null / CharField 200 | — |
| card_{1..4}_title, _line, _page, _illustration, _illustration_alt, _accent | Char / Char / FK FutureSaintsIndexPage (SET_NULL) / FK Image / Char / choice | titles from comp 01 |
| holy_land_title, _line, _page, _illustration, _illustration_alt, _accent | same | "Explore the Holy Land", accent "sand" |
| saint_of_week | FK `catalog.SaintPage`, null, SET_NULL, `limit_choices_to={"live": True}` | — |
| saint_of_week_line | CharField 160, blank | — |

The four cards and the feature card are flat discrete fields, not Orderables, because the comp has
exactly four plus one and the brief forbids a fifth small card. Orderables would invite a fifth.

**FutureSaintsIndexPage(FutureSaintsGateMixin, Page)**: `content_kind` (choice, five values),
`intro` (TextField 400), `accent` (choice), `banner_illustration` + `banner_illustration_alt`.
`parent_page_types = ["future_saints.FutureSaintsHomePage"]`; `subpage_types = []` until Phase 2.

Accent choices: `blue / sage / gold / terracotta / sand`, with a blank option (standing rule 4).

### Phase 2 (proposal only, not built in Phase 1)

`LearningPageBase(FutureSaintsGateMixin, Page)` (abstract) holds the brief §4 common fields:
student_title, subtitle, hero_illustration(+alt), index_thumbnail, explorer_intro/story,
researcher_intro/story, think_about_it, reflection_question, show_on_discovery_map,
show_on_homepage, featured_sort_order, last_source_reviewed_at.

Five concrete types, each with a typed FK to its canonical page:

| type | canonical FK | limit_choices_to |
|---|---|---|
| SaintLearningPage | `catalog.SaintPage` | `live=True` |
| MarianApparitionLearningPage | `catalog.SacredSitePage` | `live=True, category="Marian Apparition"` |
| EucharisticMiracleLearningPage | `catalog.SacredSitePage` | `live=True, category="Eucharistic Miracle"` |
| HolyLandLearningPage | `catalog.SacredSitePage` | `live=True, category="Holy Land"` |
| CaliforniaMissionLearningPage | `catalog.SacredSitePage` | `live=True, category="Shrine & Basilica", trail_stops__trail__slug="california-mission-trail"`, plus a `founding_number` (1–21, unique) editorial field, since no canonical founding-number field exists |

Repeating items are Orderables with InlinePanels (standing rule 4): `TimelineItem`, `FunFact`,
`WordToKnow`, `QuizQuestion` → `QuizAnswer` (nested via a ClusterableModel), `SourceLink`.
Phase 3: `MissionSchoolProject` (ParentalKey to the mission learning page) with `ProjectMaterial`
and `ProjectStep` Orderables, plus its own `status` choice (not_started/draft/review_ready/published)
because the brief requires a per-project status independent of page publishing.

### Phase 2a as built (PR #17), and how it differs from the proposal above

- **One reading level (owner decision).** Each explorer/researcher pair is a single field:
  `intro` (help text "50–80 words"), `story` ("250–400 words, short sentences, explain hard
  words"), `TimelineEntry.text` and `WordToKnow.definition`. The Phase 3 `MissionSchoolProject`
  uses single fields too: `project_intro`, and one `instructions` text per step.

- **The shared base is a concrete model, `LearningPage(FutureSaintsGateMixin, Page)`, not an
  abstract `LearningPageBase` (owner-accepted).** The repeating items (QuickFact, TimelineEntry,
  FunFact, WordToKnow, SourceLink, QuizQuestion → QuizChoice) need a real model for their
  `ParentalKey`, and an abstract model can't be one. The alternative, a `ParentalKey` to Wagtail's
  `Page`, would add those (empty) child lists to every adult page's revision content. A concrete
  base keeps the relations inside the Future Saints app. It is `is_creatable = False`, so editors only
  ever create the five types (`SaintLearningPage`, `MarianLearningPage`,
  `EucharisticLearningPage`, `HolyLandLearningPage`, `MissionLearningPage`); the cost is one extra
  join (multi-table inheritance) when a learning page loads.
- Names as built: `TimelineEntry` (not `TimelineItem`), `QuizChoice` (not `QuizAnswer`); Holy Land
  adds a `BibleReference` Orderable.
- Mission founding fields are on `MissionLearningPage` now: `founding_number` (1–21, validated),
  `founding_date` + `founding_date_display`, and `founding_source_note`. The canonical FK accepts
  only pages on the California Mission Trail, which excludes the duplicates 1144 and 1126.
- `show_on_discovery_map` waits for Phase 4.
- Quiz validation lives in the admin form's `is_valid()`, because a cluster form validates its
  inline formsets after `clean()`.
- Each index takes only its own type: `LearningPage.can_create_at()` compares the index's
  `content_kind`.
- `create_future_saints_tree --dry-run` prints the six pages it would create and writes nothing.

### Review: Wagtail moderation workflow (chosen)

Wagtail 7.4 has workflows enabled by default and no setting here turns them off. Plan: a "Future
Saints editorial review" Workflow with one GroupApprovalTask ("Future Saints reviewers" group),
assigned to the FutureSaintsHomePage subtree. "review_ready" = in moderation, "published" =
approved and published. Wagtail already records who approved and when (revision + workflow
state + audit log), which covers `reviewed_by`/`reviewed_at` and is better SOC 2 change-management
evidence than hand-rolled fields. Phase 1 adds the group and workflow in
`create_future_saints_tree` (idempotent), not in a data migration.

## 4. Gating

`FutureSaintsGateMixin` (future_saints/models.py) on every Future Saints page type:

- `serve()` and RoutablePage routes raise `Http404` unless `future_saints_enabled(request)`.
  Admin preview (`serve_preview`) is untouched: only signed-in editors can reach it.
- `get_sitemap_urls()` returns `[]` unless the **mode** is "on". This uses the mode, not the
  request, because crawlers are never staff. The stock `wagtail.contrib.sitemaps` view picks it up
  with no other change.
- `get_context()` sets `fs_noindex = mode != "on"`. The base template emits
  `<meta name="robots" content="noindex,nofollow">`, and `serve()` also sets
  `X-Robots-Tag: noindex, nofollow` (same header the existing NoindexMiddleware uses).
- Site search: `search/views.py` searches only the four types in `SEARCH_GROUPS`, so Future Saints
  pages are already excluded. **No change to search/views.py**; a test pins this. If they're
  added later, the queryset gets `.not_descendant_of(fs_home, inclusive=True)` before `.search()`
  while the mode isn't "on".
- `robots.txt`: no change. Pages carry noindex instead. (Adding `Disallow: /future-saints/`
  would stop crawlers from ever seeing the noindex.)

## 5. Separate base template

`templates/future_saints/base.html` does **not** extend `base.html`. It reuses only:
the skip-link markup (base.html:21) and `.sr-only`. There is no favicon partial in the repo to
reuse. It deliberately omits Google Fonts, the bare `{% csrf_token %}` (base.html:19, which sets
`csrftoken` on every adult page), the search form, the account menu, sign-in, social links,
newsletter, Support link and the DB-driven footer menus. See future-saints-affiliate-privacy-gates.md.

Logo: no SVG wordmark exists in the repo. The adult header renders `SiteSettings.logo` (a
Wagtail image; the file is `media/original_images/Logo_Header.png`) with a text fallback. The
Future Saints header uses the same `SiteSettings.logo` via `{% image %}` and the same text
fallback, followed by a real-text "Future Saints" lockup. **Owner action: an SVG master of the
wordmark, if one exists outside the repo.**

## 6. Main-site nav item (B6)

wagtailmenus items are DB-linked pages, so a DB item would bypass the switch. Instead, follow the
existing hard-appended "Blog"/"Our Story" pattern in `menus/main_menu.html:13-25` and
`menus/mobile_menu.html:9-20`: a `{% future_saints_menu_url as fs_link %}` tag returns the URL
only when `future_saints_enabled(request)` and the page is live; otherwise "". The markup sits in
`{% if fs_link %}` and is placed so that with the switch off no character of output changes. A
test diffs the adult homepage HTML against main's rendering.

show_in_menus gotcha: wagtailmenus renders sub-items only for pages with `show_in_menus=True`.
`create_future_saints_tree` leaves `show_in_menus=False` on all six Future Saints pages so that,
if someone ever adds the home as a DB menu item, no ungated child links appear under it.

## 7. Static files

Source static lives in `sitesofgrace/static/` (repo `static/` is collectstatic output), so:

- `sitesofgrace/static/css/future-saints.css` → served at `static/css/future-saints.css`
- `sitesofgrace/static/fonts/lora/Lora-{Regular,Italic,SemiBold,Bold}.woff2` + `OFL.txt`
  (Lora is SIL OFL 1.1; **not currently in the repo**. It must be fetched from the upstream
  Cyreal release. Needs owner OK; see the open questions.)
- `sitesofgrace/static/js/future-saints.js`: menu disclosure plus the reading-level control. No
  cookies and (since Phase 2a) no browser storage. Pages work without it.

Tokens (on `:root`): navy #032553, pilgrimage blue #173A61, ivory #FDF9F2, parchment #F9F1E8,
gold #C79A42, stone #5F6470. Proposed accent tints, sampled to sit with comp 01 (for approval):
blue #DCE7F2, sage #E1E8D3, gold #F3E6C6, terracotta #F2DCD0, sand #EEE5D5, each with a darker ink
for icons/rules. Comp 01's California card is lavender; the brief's accent list has no lavender,
so missions use **sand** unless you say otherwise.

## 8. Files for Phase 1

New:
```
future_saints/__init__.py
future_saints/apps.py
future_saints/switch.py
future_saints/models.py
future_saints/migrations/__init__.py
future_saints/migrations/0001_initial.py
future_saints/templatetags/__init__.py
future_saints/templatetags/future_saints_tags.py
future_saints/management/__init__.py
future_saints/management/commands/__init__.py
future_saints/management/commands/create_future_saints_tree.py
future_saints/management/commands/future_saints_dev_sample.py
future_saints/tests/__init__.py
future_saints/tests/test_switch.py
future_saints/tests/test_pages.py
future_saints/tests/test_privacy.py
future_saints/tests/test_adult_unchanged.py
future_saints/tests/test_commands.py
sitesofgrace/templates/future_saints/base.html
sitesofgrace/templates/future_saints/future_saints_home_page.html
sitesofgrace/templates/future_saints/future_saints_index_page.html
sitesofgrace/templates/future_saints/includes/_header.html
sitesofgrace/templates/future_saints/includes/_footer.html
sitesofgrace/templates/future_saints/includes/_breadcrumb.html
sitesofgrace/templates/future_saints/includes/_subject_card.html
sitesofgrace/templates/future_saints/includes/_feature_card.html
sitesofgrace/templates/future_saints/includes/_art_frame.html
sitesofgrace/templates/future_saints/includes/_reading_level.html
sitesofgrace/templates/future_saints/includes/_section_heading.html
sitesofgrace/templates/future_saints/includes/_parchment_panel.html
sitesofgrace/static/css/future-saints.css
sitesofgrace/static/js/future-saints.js
sitesofgrace/static/fonts/lora/*.woff2, OFL.txt
tools/future_saints_screens.py                (Playwright screenshots + comp side-by-side)
docs/future-saints/ (brief, comps, three audit docs, art-manifest.md, screenshots/phase1/)
```

Changed (small, additive):
```
sitesofgrace/settings/base.py                 INSTALLED_APPS += "future_saints"; SOG_FUTURE_SAINTS
sitesofgrace/templates/menus/main_menu.html   gated item (no output when off)
sitesofgrace/templates/menus/mobile_menu.html gated item (no output when off)
```

Not changed: base.html, home/models.py, catalog/*, search/*, core/v2.py, robots, sitemap
wiring, any env var or app spec.

## 9. Test plan (Phase 1)

`future_saints/tests/`: switch modes (off/staff/on/garbage) × anonymous/staff for the home and an
index; noindex meta + header until "on"; sitemap excludes the subtree until "on"; search results
never include it; adult homepage + header HTML identical to main's with switch off (and staff
header identical when off); a banned-string scan of rendered Future Saints HTML; `response.cookies`
empty for anonymous; four cards + one Holy Land feature present; reading-level buttons have
`aria-pressed` and type="button"; menu button has `aria-expanded`/`aria-controls`; command
idempotency; dev-sample refuses without DEBUG / against a non-local host.
Playwright: menu keyboard/Esc/focus return, reading-level keyboard + no cookie, check_overflow at
360/390/430, screenshots.

## 10. Open questions for the owner

1. Lora woff2: OK to download the OFL files from the upstream Lora release (Cyreal / Google Fonts
   GitHub) into `sitesofgrace/static/fonts/lora/`? That's the only external fetch Phase 1 needs.
2. Accent tints in §7, and sand (not lavender) for Missions.
3. The brief says "do not show a functional switch until both editorial versions exist". On the
   homepage, the Explorer/Researcher buttons only set a preference (sessionStorage + `?level=`), so
   Phase 1 builds them as specified. On detail pages (Phase 2) the toggle appears only when both
   stories are filled.
4. The Privacy Policy is a **draft in production** (id 2502) and absent locally, so the footer
   link renders as the staff-only warning chip for now. The brief also needs a children's-section
   privacy note, which isn't in `legal/content/` yet. Counsel item.
