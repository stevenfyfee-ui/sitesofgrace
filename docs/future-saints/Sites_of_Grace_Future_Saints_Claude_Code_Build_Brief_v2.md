# SITES OF GRACE — FUTURE SAINTS
## Claude Code implementation specification, v2.0 — November 5, 2026

**Brand name:** Future Saints — APPROVED (no longer provisional)
**Parent site:** Sites of Grace (`https://sitesofgrace.com`)
**Audience:** Primarily grades 2–5, with useful resources for parents, teachers, Catholic schools, homeschooling and parish religious education
**Base URL:** proposed `/future-saints/` (audit route constraints before implementation)
**Status:** APPROVED CONCEPT / NOT AUTHORIZED FOR PUBLIC DEPLOYMENT
**Priority:** preserve existing site and content; no travel features in Future Saints; build in gated, reviewable phases

> FOR CLAUDE CODE: Read this whole specification and review the three exact screenshots in `design_references/` BEFORE changing files. Audit the actual repository/models/templates first. This is an existing custom Sites of Grace implementation. Do not assume WordPress or invent a framework. Do not merge, deploy, alter production feature flags, enable any commerce feature, or expose child routes to the public without explicit owner approval.

---

## 1. APPROVED DECISIONS: DO NOT REOPEN BY DEFAULT

1. The children's learning area is **Future Saints**. Branding displayed as **Sites of Grace | Future Saints**.
2. **One consistent look and feel throughout the section**: the three attached approved designs are the source of truth for visual style, not the later playful/cartoony variants.
3. **ONE template per content type**, with shared structure but unique thematic art and a few type-specific educational blocks:
   - Saint biography (match the attached St. Carlo Acutis mockup closely)
   - Marian apparition
   - Eucharistic miracle
   - Holy Land site
   - California mission
4. **Dedicated California Missions homepage** with a watercolor-illustrated California map of **all 21 historic Alta California missions**; select a mission and show a detail/summary panel as in the approved screenshot.
5. **No travel content** anywhere in Future Saints: no flights, hotels, restaurants, lodging, itineraries, booking, trip planner, cost estimator, travel affiliate promotions, or live travel map controls.
6. Maintain two reading levels (Grades 2–3, Explorer; Grades 4–5, Researcher) within the SAME design, not distinct themes or layouts.
7. Reusable five-question quizzes with friendly explanatory feedback and printable research sheets, with no student accounts or score storage.
8. Include **mission model/project-building instructions for each individual California mission** and a project hub/guide on the California Missions landing page.
9. **Amazon Associates links must NOT be enabled within Future Saints**. See the important compliance block below; do not treat a separate parent page as an automatic fix.
10. Reuse the existing Sites of Grace published canonical data and source research, adding a human-reviewed child-education editorial layer, not a duplicate independent research database.

**Interpretation of a wording ambiguity:** the owner mentioned mission-building instructions “for saints pages.” Because these are projects for California schools about specific missions, implement the instructions on **individual California MISSION pages**, plus the Missions homepage. A related saint biography (e.g., St. Junípero Serra) can link to the Missions education hub but should not acquire a generic mission-project editor.

---

## 2. DESIGN SYSTEM AND APPROVED SCREENSHOTS

### Files in this package

- `design_references/01-future-saints-homepage.png` — authoritative homepage reference. Keep the map hero, original four featured subject cards, large readable type, navy logo bar, ivory background, gold/powder-blue accents, Saint of the Week and reading-level selection. Change the word **Kids** to **Future Saints**.
- `design_references/02-california-missions-hub.png` — authoritative mission hub reference. Keep the illustrated California map at left, featured selected mission panel at right, and lower educational action cards. Change **Kids** to **Future Saints**. Artwork is a *visual inspiration*, not an accurate mission-pin dataset.
- `design_references/03-st-carlo-biography.png` — authoritative saint PROFILE layout reference. Large left portrait with contextual imagery, prominent title, story next to a quick-facts panel, lower Story/Timeline/Fun Facts/Quiz cards, reflection strip, reading-level toggle, Print Research Sheet. Change **Kids** to **Future Saints**.

**Important:** the screenshots are *reference comps*, not images to stretch into page backgrounds. Implement actual semantic HTML/components, editable text, accessible buttons and separately created appropriately licensed artwork. Use the actual original Sites of Grace wordmark/logo from the repository, not the imperfect generated logo typography in screenshot composites.

### Brand palette

- Deep Marian Navy: `#032553`
- Pilgrimage Blue: `#173A61`
- Sacred Ivory: `#FDF9F2`
- Pilgrim Parchment: `#F9F1E8`
- Soft Sacred Gold: `#C79A42`
- Stone Gray: `#5F6470`
- Type-specific secondary accents, sparingly: blue, sage, warm gold, terracotta, stone/sand. No bright preschool palette and no childish character mascots.

Typography: readable serif headings, highly legible body text, line-height suited to children's reading, large touch targets, restrained textures. Avoid decorative texture behind long paragraphs. Use one consistent header/nav/footer/card family and shared grid/spacing system. Five variants should feel like sibling templates, not five unrelated websites.

### Homepage and navigation

Home headline: **Explore the Wonders of Our Faith!**
Subheading: **Amazing stories, holy people, and places to discover.**

Retain the four prominent cards from the approved homepage artwork:
1. Meet the Saints
2. Mary & Apparitions
3. Eucharistic Miracles
4. California Missions

**Holy Land is newly required:** add a fifth subject entry without compressing the original four attractive cards into five tiny desktop cards. Recommended: add a full-width, illustrated **Explore the Holy Land** feature card directly below the original four, before the Saint of the Week/quiz/map area. In navigation, give Holy Land equal standing among subjects; if necessary use a compact top-level Explore dropdown. Responsive layouts should avoid horizontal scroll.

Other homepage blocks: Explorer/Researcher reading-level control; Saint of the Week; illustrated World Discovery Map preview; Take a Quiz. Remove adult-booking / shop / travel CTAs in this section.

### Type-specific differences (same design, a distinct editorial personality)

| Content type | Visual accent / hero | Unique educational focus |
|---|---|---|
| Saints | Original **Carlo Acutis** visual layout, large illustrated saint portrait, gold/blue | Life, key virtues, feast day, acts of charity, saintly example, “Think About It” |
| Marian apparitions | Marian blue, roses, stars, recognizable apparition setting, Mary in hero | Visionary/witness, date, message, local event, Church's assessed status, prayer/reflection |
| Eucharistic miracles | Gold/ivory, host/chalice/monstrance imagery, subdued rays | Catholic Eucharistic teaching, what was reported, source evidence and Church's assessment, where/how remembered |
| Holy Land sites | Sandstone/olive/sage, Biblical-era geography, relevant building/landscape | What happened in Scripture, biblical passage, history vs tradition, people, why it matters |
| California missions | Parchment/copper/sage, mission silhouette/facade, poppies, historical scene | Founding, mission names/order, Native peoples, daily life, difficult history, architecture, **Build This Mission** |

No special one-off page layout for St. Carlo: he is the REFERENCE INSTANCE of the reusable Saints template.

---

## 3. INFORMATION ARCHITECTURE / ROUTES

Proposed, configurable paths (inspect existing route namespace before implementation):

```
/future-saints/                                 Home
/future-saints/saints/                          Saints index
/future-saints/saints/<slug>/                   One saints profile template
/future-saints/marian-apparitions/              Marian index
/future-saints/marian-apparitions/<slug>/       One apparition template
/future-saints/eucharistic-miracles/            Eucharistic miracle index
/future-saints/eucharistic-miracles/<slug>/     One miracle template
/future-saints/holy-land/                       Holy Land index
/future-saints/holy-land/<slug>/                One Holy Land site template
/future-saints/california-missions/            Missions home + illustrated map of all 21
/future-saints/california-missions/<slug>/     One mission template WITH project instructions
/future-saints/california-missions/projects/   GENERAL mission school-project guide
/future-saints/map/                             World Discovery Map
```

Optional component endpoints/print views may be under corresponding pages. Keep canonical linking and breadcrumbs; staff previews hidden behind flag and existing permissions. Use a conventional URL design, not a separate new domain.

**No travel data shown**, even if a canonical destination model contains travel, stay, lodging, transportation, pricing, or pilgrimage itinerary fields. Never render those source fields or re-use the travel-page template in Future Saints.

---

## 4. DATA REUSE AND EDITORIAL / ADMIN MODEL

Audit actual Django/Wagtail or other existing backend first—do not assume implementation details based on production admin URLs alone. Identify existing saints, apparition, miracle, site, trail and geographic records; verify which of the 21 missions are present. Identify editorial/admin patterns and existing asset storage.

### Suggested content abstraction — adapt to actual models

`FutureSaintsLearningPage` or equivalent child companion linked to canonical record:

- `content_kind` (saint / marian_apparition / eucharistic_miracle / holy_land / california_mission)
- Validated, typed `canonical_content_reference` (or explicit FKs), not unverified string slugs/hard-coded IDs
- `slug`, `published`, `reviewed_by`, `reviewed_at`, `last_source_reviewed_at`
- `student_title`, `subtitle`, `hero_illustration`, `hero_illustration_alt`, `index_thumbnail`
- `explorer_story`, `researcher_story`; optional shorter intro for both
- `key_facts`, `timeline`, `fun_facts`, `words_to_know`, `think_about_it`, `reflection_question`
- `source_links` and per-claim/source notes; status/evidence attribution where applicable
- `quiz_questions` (five per profile) with explanatory correct-answer feedback
- `show_on_discovery_map`, `show_on_homepage`, `featured_sort_order`
- Optional type-specific fields below; validation should permit phased completion in staff mode but bar publicly published partial records.

Read-only inherited fields from current published records where possible: proper name, canonical references, dates, feast day, coordinates, mission founding date, type, related locations, recognition status, sources. Do NOT blindly duplicate or mutate adult records. Children-facing prose, reflection prompts and quiz choices must be edited and approved by staff; no live AI-generated fact text.

### Type-specific editorial fields

**Saints:** early life; response to God's call; important actions; feast day; patronage when established; virtues; related places; saint's quote only when verifiably sourced; optional “Try a small act of kindness” prompt.

**Marian apparitions:** date/place; witnesses; summary of claimed apparitions; main message; Church recognition and its precise meaning; prayer and devotion; careful distinction between approved/recognized devotion, a reported event, and proof of supernatural origin.

**Eucharistic miracles:** historical report; context; Church's view; sources and evidence claims; Catholic belief about Real Presence; vocabulary; avoid overstating laboratory/scientific claims.

**Holy Land:** Biblical passage citations (link to reputable Catholic Scripture resources), event; what scholars/historians know; traditional site identification where uncertain; relevant people; historical period; map location; reflection; Jewish/Christian/Muslim significance presented appropriately where relevant.

**California mission:** official name; alternate name; foundation number/order; foundation date; founder(s) as supported; location; Indigenous community name(s) and history; mission life; church architecture; current historical significance; founding-order timeline; **dedicated optional mission model project** attached to the mission (below).

### Reading levels

The visual shell never changes. Switch between:
- **Explorer — Grades 2–3:** roughly 150–250 words, short sentences, definitions, shorter timelines.
- **Researcher — Grades 4–5:** roughly 300–500 words, dates, some broader context, richer vocabulary.

Keep factual integrity the same in both. Never misrepresent a challenging historical fact to make a story cheerier. Do not show a functional switch until both editorial versions exist. No registration, age-question, saved preference tied to a child, or personal data collection.

---

## 5. THE FIVE DETAIL TEMPLATES — REQUIRED COMPONENTS

### A. Saints detail template (MATCH APPROVED CARLO MOCKUP)

1. Same SOG/Future Saints navy navigation and breadcrumb.
2. Grades 2–3 / 4–5 switch and printable research sheet control.
3. Large saint portrait on the left; prominently placed “Meet Saint [name]” and subtitle.
4. Readable “His/Her Story” introduction or main narrative beside the portrait.
5. “Quick Facts” parchment panel (life dates, home, feast day, known for/patronage).
6. Exactly the original four learning navigation cards (Story, Timeline, Fun Facts, Quiz); additional vocabulary and sources may appear below the fold.
7. Full reading section, timeline, fun facts, Words to Know and reflection.
8. “Think About It” footer/banner with a question linked to holiness.
9. 5-question quiz and printable sheet. Avoid reducing story to a superficial quiz.
10. St. Carlo Acutis is the first real seed page; remaining saints use the identical template, not another bespoke Carlo page.

### B. Marian apparition detail template

Use SAME spatial rhythm and components as saints but with a Mary-specific blue/cream illustration treatment. Header title e.g. “Our Lady of Lourdes.” Intro + “The Story” + quick facts (when/where/witnesses). Learning cards: The Story / Timeline / Mary's Message / Quiz. Lower blocks: witnesses, prayer, Words to Know, Church recognition status (carefully worded), sources. Match watercolor art quality; avoid infantilizing Mary or falsely suggesting every claimed apparition has the same Church approval.

### C. Eucharistic miracle detail template

Same common structure; gold/ivory accents, historically appropriate illustration. Hero + story + quick facts (place/time/event), cards “The Story / What Happened? / Why It Matters / Quiz” or equivalent. Include Catholic Eucharistic teaching in a child-readable box; indicate what was reported as a historical/devotional claim, plus how Church sources understand it. Do not present unverified scientific claims as definitive. Include fun facts, timeline, sources and print sheet.

### D. Holy Land site detail template

Same shared shell with olive/sand tones, illustrated region or site. Hero + story + quick facts, four learning cards (“Bible Story / Timeline / People & Places / Quiz”). Add “Find It in the Bible” with book/chapter/verse links, “Then and Now” historical comparison (NOT travel), and “What is known vs. traditional identification.” No travel, visits or visa data. An accessible illustrated map locator can link to the world map.

### E. California mission detail template

Same design family, featured architecture illustration and quick facts (mission name, founded year, founding order, location, named-for saint), timeline, rich educational story, **Indigenous peoples and mission history** section, vocabulary, fun facts, quiz, printable research sheet, and a separate **“Build This Mission”** project area. Main learning cards can be “Mission Story / Timeline / Native Peoples / Build & Quiz” with clear entry to project; preserve the overall four-card visual structure.

Projects are tied to the CURRENT mission and must feature its distinguishing facade/architectural elements. No generic project image quietly reused for every mission.

---

## 6. CALIFORNIA MISSIONS HOMEPAGE (SPECIAL MAP HUB)

Make `/future-saints/california-missions/` match `02-california-missions-hub.png`:

- Title “Discover the 21 California Missions.”
- Primary illustrated watercolor California map with **all 21 clickable mission pins**.
- Distinguish chronological founding number from south-to-north geographic ordering; use historical founding numbers only when labeled as such.
- On selecting a mission, show a large right-hand mission preview: illustration/photo, name, founded date, age-appropriate introduction, “Read & Learn”, and optional “Build This Mission” link only if project is published.
- On narrow screens, selected mission panel appears below map or in an accessible sheet; no map-element overlap blocking interactions.
- Under the illustrated map, use the four design-family action cards: Mission Stories, Timeline, Native Peoples, Test Your Knowledge.
- Additional **Mission School Projects** card/banner that links to the GENERAL project guide (do not try to fit five tiny equal cards into the approved 4-card row).
- Optional alphabetical list and founder-order list for accessibility and school research; every one of 21 should be findable without map gestures.

**Location accuracy is non-negotiable.** The screenshot is an artistic conceptual visual, not a validated 21-point basemap. All pin centers must align to a verified projection/control points and canonical coordinates; verify southern and northern extremes and Monterey/San Francisco/Los Angeles clusters. Provide an ordered list and close-pin selection strategy for mobile. The 21 California missions are the Alta California chain founded 1769–1823 (not an arbitrary map of all missions in Baja California as well).

Useful source for independent mission-name/founding-order verification: California State Parks, https://www.parks.ca.gov/?page_id=22679 and https://www.parks.ca.gov/?lang=en&page_id=22722 . Historical interpretation must use additional Native-authored or museum/institutional sources, e.g. California Museum https://californiamuseum.org/exhibitions/signature/california-missions/ .

### Explicit responsible history requirements

The missions have Christian and colonial history. Explain missionaries' faith and the buildings' Catholic significance without portraying mission life as universally voluntary, idyllic, or culturally neutral. Name local Indigenous communities with source support; describe coerced labor, disease, restrictions, resistance, loss and survival in developmentally appropriate language. Avoid phrases suggesting Indigenous peoples had no skills, beliefs or communities before the missions. Distinguish construction/founding from present rebuilt/restored buildings and from historic church facades when creating models.

---

## 7. CALIFORNIA SCHOOL MISSION MODEL PROJECTS

### Mission-specific project module

On each individual mission page, optionally display “Build This Mission: [Mission Name]” with:

- Grade guidance (typically grade 4 but accessible across 2–5), difficulty, estimated *hands-on* stages rather than fabricated precise time estimates.
- Mission-specific reference photo/illustration with source/rights and correct modern/historic identification.
- **What makes this mission distinct:** bell tower count/shape, arch arrangement, facade, roofline, mission grounds as supported by sources.
- Materials checklist with quantities/options and safe substitute materials (e.g., cardboard, kraft paper, non-toxic glue, washable paint, craft sticks, model clay).
- Step-by-step instructions broken into 5–10 child-readable stages, each with optional sketch/diagram, adult supervision if tools are needed.
- Choice of cardboard model / shoebox diorama; no dangerous tools or candles required. Clearly distinguish adult-only tasks, especially box cutters, hot glue, hobby knives.
- Printable **materials checklist**, **model-building instructions**, and a mission **fact card** to display alongside finished model.
- Optional photos of the finished model if properly licensed and owner uploaded. No child uploads or public project gallery.
- Bibliography/primary sources. Never fill missing historical details with guesses.
- Per-mission admin status: `not_started`, `draft`, `review_ready`, `published`.

**General Projects page** `/future-saints/california-missions/projects/`:
- “How to Build a California Mission Model” general introduction.
- Beginner cardboard model instructions, safety tips, project-planning steps.
- Materials list (free editorial text; no purchase pressure).
- 21 mission selection grid linking to each available project guide; unfinished projects show “Guide coming soon” or simply no project CTA (configurable, no broken links).
- General printable checklist and student research sheet.
- Student-facing text: use supplies you already have at home when possible; adult help for shopping/cutting.

### Admin-editable fields

Prefer `MissionSchoolProject` related one-to-one/one-to-many with existing mission companion:

```
mission_learning_page (validated relation)
project_title
status
project_intro_explorer
project_intro_researcher
model_reference_image + alt + copyright/source credit
historical_vs_restored_note
architectural_features[]
materials[] {item, quantity, optional_alternative, safety_note}
steps[] {order, title, instructions_explorer, instructions_researcher, optional_image, safety_note}
finishing_tips
adult_supervision_notes
printable_fact_card_fields
sources[]
last_reviewed_at
```

Make these cleanly editable from staff admin (inline material/step forms if supported). Provide validation for published project (at least one reference, 3+ steps, material list, sources, and safety review). Do not require images for incomplete staff drafts.

### CRITICAL: AMAZON ASSOCIATES / CHILD-DIRECTED CONTENT

**Blocked feature: affiliate links or Amazon product widgets on Future Saints pages.** As of policy current April 14, 2026, Amazon's Associates suitability rules explicitly exclude sites **directed toward children**. Future Saints is unambiguously directed toward children under 13. It is not sufficient to put a disclosure or call the link “for parents.” Moving links to a parent page on the same domain may NOT resolve site-wide eligibility; require written clarification from Amazon and legal review before implementing a monetized flow. Do not assume a generic parent gate or link shield solves it.

Official policy: https://affiliate-program.amazon.com/help/operating/policies (Participation Requirements, unsuitable sites paragraph f)
Official agreement/disclosure: https://affiliate-program.amazon.com/help/operating/agreement
FTC child-directed analysis: https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions

**Build for now:** educational materials lists and staff-editable project guidance only. A separately governed adult Parent & Teacher Resources concept can be noted in documentation (without affiliate links). **Do not render merchant logos, Amazon tags, affiliate links, purchasable product recommendations or checkout prompts anywhere within Future Saints, and do not insert affiliate links in printed sheets.** Document a future authorization gate requiring explicit Amazon clarification and owner approval.

---

## 8. ILLUSTRATED MAPS — FUNCTIONAL, NOT LEAFLET

No Leaflet/Mapbox/Google tiles and no reuse of the adult site's slippy map UI. Build a bespoke responsive SVG illustrated geography layer with interactive semantic markers and separate accessible results list.

### World Discovery Map

- Illustrated, watercolor world view consistent with the homepage map hero.
- Topic filters: Saints, Marian Apparitions, Eucharistic Miracles, Holy Land Sites, California Missions (missions can appear as a regional cluster/one callout and link to dedicated California map; don't pile 21 tiny dots on the world overview).
- On click/tap/keyboard, open a short accessible story-card preview, with “Read the Story.”
- Only published child learning pages show as navigable; unpublished canonical sites must not create broken links.
- Map icons must be recognizable and large enough for touch; accessible list always available.
- No adult travel/popups/bookings and no geolocation permissions.

### California Missions Map

- Original illustrated California silhouette / terrain with 21 distinct accurate markers.
- Geography control-point or projection calibration documented and tested; overlay placed in the same coordinate viewbox as illustration.
- Selected mission card is the editorial view, not an adult navigation popup. For mobile, map with scrollable list and selected panel below.
- Founding order shown explicitly as **Founding #**, not mistaken for geographic stop order.

### Technical requirements

- Reuse canonical lat/lon; create an explicit calibration/override data file or admin adjustment record only when necessary, with review flag, never guess locations.
- Differentiate decorative art from interactive overlay; use stable SVG viewBox and `preserveAspectRatio`.
- Keyboard focus order, buttons with aria-label, accessible list/fallback; no hover-only interactions.
- Support reduced motion; gentle optional marker emphasis (not constant motion), no confusing animations.
- Handle close-together pins on mobile via focused selection/list; no fake pins, geographic labels or mystery icons.
- Strong test coverage for viewport sizes 1440, 1024, 768, 430, 390, 360.
- Dynamic map images must be separate, appropriately licensed assets, not flattened full page comps.

---

## 9. QUIZZES / RESEARCH / PRINT / SAFETY

Reusable quiz: five multiple-choice questions, 3–4 answers, explanation for each correct answer and nonpunitive feedback, next, finish, retry; client-only state. No leaderboard, account, child identity, persistent server score or analytics tied to a child. Sanitize all user-facing content; no student-generated input required.

Printable research sheet: one or two pages, US Letter and A4 friendly, title/location, historical facts, dates, short timeline, key vocabulary, five major learning points, sources/credits, reflection space. Mission pages also offer **Model Project Checklist / Instructions / Fact Card**, printed as needed. Standard browser print should work; don't assume a PDF library is required.

No child signups, newsletter forms, donations, ads, chat, location prompts, comment threads, personalization profiles, social widgets or external purchase prompts. Audit what child routes inherit from main shared site templates: analytics, tags, advertisements, third-party font resources, cookies and persistent IDs. COPPA-focused review and clear child-section privacy disclosure link before public launch. No automatic claim of COPPA compliance.

Use credible Catholic and historical sources, with linked references; direct Scripture passages to reputable Catholic text sources. Have human editorial review before making content public. Avoid fabricated quotes and devotion-status assertions.

---

## 10. PHASED BUILD / OWNER REVIEW GATES

### Phase 0 — repository audit and acceptance plan (DO FIRST)

- Examine actual codebase, route resolution, content models, CMS snippets/admin, current main site assets, quiz or print infrastructure, existing map utilities, existing canonical site/saint data, media license patterns, feature flags and staff preview mechanism.
- Identify all existing canonical records for: St. Carlo Acutis; Our Lady of Lourdes; Eucharistic Miracle of Lanciano; a Holy Land site e.g. Church of the Holy Sepulchre; Mission San Diego de Alcalá; and all 21 historic California missions.
- Report exactly which records and fields are present or missing. Avoid inventing missing data or claiming all mission pages exist.
- Document migrations, data associations, image needs, script/cookie privacy risks, and test plan.
- Create `docs/future-saints-architecture.md`, `docs/future-saints-content-audit.md`, `docs/future-saints-affiliate-privacy-gates.md`.
- Work in reviewable branch; no production change in this phase.

**Owner gate:** approve the architecture/data-reuse approach and the exact foundation files to change.

### Phase 1 — common shell + homepage + basic indexes

- Build behind isolated feature flag e.g. `SOG_FUTURE_SAINTS`, default off for public; staff-only review.
- Global Future Saints header/nav/footer, typography/color tokens, reusable cards, responsive components.
- Homepage matching approved 01 screenshot. Keep original four-card top row and a separately styled Holy Land feature.
- Five subject indexes in common design family; feature flags on unfinished page controls.
- Child-specific privacy-safe template boundary; no existing adult travel CTA leakage.
- Screenshot QA at 1440/1024/768/390/360.

**Owner gate:** approve overall design and the new Holy Land placement.

### Phase 2 — five reusable templates and one real example each

- Add/extend child learning content admin and type-specific fields.
- Implement exactly five templates, not unique per-record layouts.
- Seed one **real, reviewed** example for each:
  1. St. Carlo Acutis (saints template EXACT visual reference)
  2. Our Lady of Lourdes (Marian template)
  3. Eucharistic Miracle of Lanciano (miracle template)
  4. Church of the Holy Sepulchre or another verified existing Holy Land site (Holy Land template)
  5. Mission San Diego de Alcalá (Mission template)
- Switcher with both edited reading levels; timeline, Quick Facts, sources, child-friendly reflection, five-question quiz, print views.
- Import only verified source fields. Staff previews require review status, don't auto-publish.

**Owner gate:** owner reviews all five example page types for design distinction and historical/doctrinal accuracy.

### Phase 3 — Missions hub + mission project authoring

- Dedicated California Missions homepage matching approved 02 screenshot, clickable illustrated map of all 21.
- Verified geographic pins and accessible alternate list; clear founded year and founding sequence.
- General California School Mission Project guide and “Build This Mission” module per individual mission.
- End-to-end sample Mission San Diego project (historically specific materials, steps, model image, checklist, PDF via print), in staff preview.
- Material lists only, no product/affiliate URLs or commerce banners.
- Audit/verify all 21 mission identity/founding records and record any missing content.

**Owner gate:** approve actual 21-pin map and sample model instructions before mass rollout.

### Phase 4 — World Discovery Map + content expansion

- Illustrated world SVG, five topic filters, selected story cards, region/marker positioning, accessible list.
- Expand all 21 mission child profiles and then high-priority saints / Marian / miracle / Holy Land items through editorial review; no auto-publish from AI drafts.
- Quizzes and school research sheets for each published record.
- Add featured editorial controls for home Saint of the Week and featured sites.

**Owner gate:** review full content QA; geography/stories verified.

### Phase 5 — regression, privacy/legal, controlled rollout

- Tests for 360/390/430 mobile and 768/1024/1440 layouts; keyboard, screen readers, print, reduced motion, color contrast, click/tap.
- Check all five templates, subject indexes, canonical links, maps, mission project guides and quiz.
- Privacy/security review: zero child profiles/accounts, no Amazon pixels or affiliate links, cookie/third-party resource inventory, reviewed privacy notice.
- Re-run adult site regression tests. DO NOT change main adult `/plan/`, planner flag, main Leaflet map, booking link status, travel pages or related admin workflows.
- Staff-only flag first; only explicit owner approval allows PR merge / public flag change.

---

## 11. ACCEPTANCE CRITERIA (DEFINITION OF DONE)

1. Header reads **Sites of Grace | Future Saints**; no visible “Sites of Grace Kids” as the section title; approved aesthetic preserved.
2. One canonical Saints page layout matches Carlo mockup, used for all saints; exactly one cohesive type template for each Marian, Eucharistic, Holy Land, and mission category.
3. `/future-saints/` has four featured cards matching visual reference plus an additional Holy Land block that does not break them.
4. Every learning profile has Quick Facts, engaging story, timeline, fun facts/vocabulary as relevant, reflection, five-question quiz, print research sheet and reputable sources.
5. Only grade-level reading content changes when toggle switches; same layout remains for both grades; no invented factual simplifications.
6. California Mission Trail landing page shows **21 accurately placed** mission selections and selected mission panel with founding details; every item is accessible via text list.
7. On each mission page a staff author can add mission-specific model project instructions, materials checklist, architectural features, reference image/sources, student safety notes and printable guide. Sample project for San Diego is demonstrably distinct.
8. General mission school-project hub exists; no affiliate links or shopping CTAs on child routes.
9. World map uses illustrative SVG, not the adult map, and includes Holy Land as a category; children never see lodging/trip/booking options.
10. Staff can author/edit/review content and projects; published child content references canonical source records without duplicating source facts unnecessarily.
11. No breaking changes to existing Sites of Grace adult routes, planner, maps, navigation, booking toggles or admin data.
12. All features staff-only until explicit approval. Repository audit, content audit, legal/affiliate gate note, screenshots and tests are delivered with the PR.

---

## 12. IMPLEMENTATION PROMPT FOR CLAUDE CODE

Copy this message into Claude Code with this package extracted in the repository root:

> Implement the **Sites of Grace | Future Saints** educational area according to `Sites_of_Grace_Future_Saints_Claude_Code_Build_Brief_v2.md`. Read ALL sections and inspect the three images in `design_references/`. The name **Future Saints** is final. The Saint Carlo mockup is the exact recurring layout for EVERY saint profile; separate but strongly coordinated templates are required for Marian apparitions, Eucharistic miracles, Holy Land sites, and California missions. Build a dedicated California Missions homepage showing all 21 missions and add a unique **Build This Mission** school-project authoring module to individual mission pages and a general projects guide. NO TRAVEL DATA OR CTAs on Future Saints. Crucially, Amazon Associates rules exclude child-directed sites: implement ONLY free educational materials lists, NO affiliate/product/merchant links and no shopping path until separate legal/policy clearance. Start with **Phase 0 repository audit** and a proposal of exact files/models/URLs, then implement only the staff-gated **Phase 1 shell/homepage** on a reviewable branch, with tests and screenshots. Do not merge, deploy or enable for public users. Preserve all adult-site functionality and flags. Report missing facts/assets rather than inventing them.

---

## 13. PRIMARY POLICY / HISTORICAL REFERENCE URLS

- Amazon Associates current program policies: https://affiliate-program.amazon.com/help/operating/policies
- Amazon Associates operating agreement: https://affiliate-program.amazon.com/help/operating/agreement
- FTC COPPA guide: https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions
- FTC COPPA privacy policy for child sections: https://www.ftc.gov/business-guidance/resources/childrens-online-privacy-protection-rule-six-step-compliance-plan-your-business
- California State Parks — 21 missions: https://www.parks.ca.gov/?page_id=22679
- California State Parks — mission trail: https://www.parks.ca.gov/?lang=en&page_id=22722
- California Museum — Missions / Indigenous history: https://californiamuseum.org/exhibitions/signature/california-missions/

*This build specification is an implementation plan, not a formal legal determination. Obtain counsel/official program clarification for affiliate eligibility and children's privacy before a public launch.*
