# Future Saints: content audit (Phase 0)

Audited 2026-11-05. Local DB = this laptop's dev Postgres. Production = read-only shell queries through
`tools/prod_run.sh` (SELECTs only, run after deployment 71f0da2b went ACTIVE). Nothing was written
anywhere.

**Local and production page IDs differ for most records** (e.g. Mission San Diego is 1357 locally
and 1310 in production). Future Saints FKs must be set through the admin chooser in each
environment, never by hard-coded ID. The local DB is also behind production (no Carlo Acutis
locally, no LegalPages, fewer saint drafts). Standing rule 10 forbids copying production data down,
so Phase 2 seeding of Carlo locally needs his page imported through the normal import path.

## A1. Canonical models

| content | app.model | parent type (slug) | URL pattern | prod total / live | local total / live |
|---|---|---|---|---|---|
| Saints | `catalog.SaintPage` | StandardPage `saints` (under learn) | `/learn/saints/<slug>/` | 500 / 212 | 211 / 211 |
| Marian apparitions | `catalog.SacredSitePage`, category "Marian Apparition" | StandardPage `marian-apparitions` | `/explore/marian-apparitions/<slug>/` | 20 / 20 | 20 / 20 |
| Eucharistic miracles | `catalog.SacredSitePage`, "Eucharistic Miracle" | StandardPage `eucharistic-miracles` | `/explore/eucharistic-miracles/<slug>/` | 33 / 33 | 33 / 33 |
| Holy Land | `catalog.SacredSitePage`, "Holy Land" | StandardPage `holy-lands` | `/explore/holy-lands/<slug>/` | 17 / 17 | 17 / 17 |
| California missions | `catalog.SacredSitePage`, "Shrine & Basilica" | StandardPage `shrines-and-basilicas` | `/explore/shrines-and-basilicas/<slug>/` | (in 52 / 52) | (in 53 / 53) |
| Saint tombs / shrines | `catalog.SacredSitePage`, "Saints & Tombs" | StandardPage `saints-and-tombs` | `/explore/saints-and-tombs/<slug>/` | 119 / 118 | 119 / 119 |
| Mission Trail (route) | `catalog.PilgrimageTrailPage` + `TrailStop` Orderable | — | `.../california-mission-trail/` | 1 trail, 21 stops | same |

There is **no dedicated mission model** and **no founding-number field**. The 21 missions are
SacredSitePages, findable as the 21 `site` FKs of the `california-mission-trail` TrailStops. Stop
order is geographic (south → north), **not** founding order.

Other models checked and not relevant: `destinations.DestinationHubPage` (travel hub; must not be
used), `learning.LearnPage` (adult articles), `catalog.Topic` (snippet tags), `home.FeaturedSaint`.

### Field map: what Future Saints may inherit read-only

SaintPage:

| need | field | inherit? | note |
|---|---|---|---|
| name | `title` | yes | |
| dates | `born`, `died` (free-text CharFields) | yes, as display text | Not structured dates. Shown verbatim in Quick Facts. |
| feast day | `feast_day` | yes | |
| patronage | `patronage` (TextField) | **edit first** | Often a long adult list. Child page gets its own `known_for` line. |
| canonization | `canonized` (CharField) | yes, short | |
| order / burial | `religious_order`, `burial_place` | optional | |
| portrait | `portrait` (FK Image) + `portrait_credit` (CharField) | yes, **only when `portrait_credit` is filled** | `portrait_url` is the source URL. Wagtail Image has no credit/licence fields of its own. |
| sources | `source_url`, `source_note` | yes, in Sources | |
| summary | `significance` (TextField) | **no, adult prose** | |
| body | `body` (RichText) | **no, adult prose** | |
| internal | `data_status`, `editor_notes`, `wikidata_id` | never rendered | |

SacredSitePage (apparitions, miracles, Holy Land, missions):

| need | field | inherit? | note |
|---|---|---|---|
| name | `title` | yes | |
| place | `locality`, `country`, `country_code` | yes | |
| lat/lng | `latitude`, `longitude` | yes (maps, Phase 3–4) | |
| date / founding | `date_display` (free text, e.g. "Founded July 16, 1769") | yes, verbatim | No structured founding date. |
| feast | `feast_day` | yes | |
| Church status | `canonical_status` (2024 DDF *Norms* terms + legacy), `recognition_year` | yes, via the existing `CANONICAL_STATUS_LABELS` plain-English map | Child copy needs its own wording of what the status means. |
| eucharistic kind | `eucharistic_kind` (miracle / precious-blood / tradition) | yes | |
| people | `associated_saint`, `related_saints` | yes (links) | |
| sources | `primary_references` (RichText) | yes, in Sources | |
| image | `featured_image` (FK Image) | **no until a credit exists** | There's no credit/licence field for featured_image. |
| summary | `summary_short` | **no, adult prose** | Editorial reference only. |
| prose | `the_story`, `church_recognition`, `catholic_teaching`, `go_deeper`, `account_tradition`, `account_church_judgment`, `account_findings`, `account_teaching`, `prep_prayer`, `prep_readings` | **no, adult prose** | Source material for editors. Never rendered to children. |
| **travel (banned)** | `pilgrimage_info`, `location_link`, `quick_*`, `address`, `time_needed`, `visit_length`, `admission`, `reservation_required`, `accessibility_*`, `worship_*`, travel/lodging/map-point Orderables | **never** | Brief §3. |
| internal | `notes_internal`, `reviewed_*_on` | never | |

## A2. Specific records (production; local differences noted)

| record | prod id | slug | state | URL | filled (of audited fields) | image + credit |
|---|---|---|---|---|---|---|
| St. Carlo Acutis | 2247 | st-carlo-acutis | live | /learn/saints/st-carlo-acutis/ | feast_day, born, died, canonized, patronage, significance, body, portrait, source_note. **Missing: source_url, portrait_credit** | portrait img#43 "CarloAcutis", **no credit** |
| (local) | — | — | **absent** | | | |
| St. Francis of Assisi | 953 (same locally) | st-francis-of-assisi | live | /learn/saints/st-francis-of-assisi/ | feast_day, born, died, canonized, patronage, significance, body, source_url, source_note | **no portrait** |
| Our Lady of Lourdes | 1091 (same) | lourdes | live | /explore/marian-apparitions/lourdes/ | everything audited, incl. recognition_year, all four account_* fields, primary_references | featured img#25 (prod only), **no credit field** |
| Eucharistic Miracle of Lanciano | 1105 (same) | eucharistic-miracle-of-lanciano | live | /explore/eucharistic-miracles/eucharistic-miracle-of-lanciano/ | core + story fields, eucharistic_kind (prod only). **Missing: recognition_year, account_*, primary_references** | img#30 (prod only), no credit field |
| Church of the Holy Sepulchre | 1128 (same) | church-of-the-holy-sepulchre | live | /explore/holy-lands/church-of-the-holy-sepulchre/ | core + story. **Missing: feast_day, associated_saint, account_*, primary_references, image** | none |
| Basilica of the Annunciation (Nazareth) | 1130 (same) | basilica-of-the-annunciation | live | /explore/holy-lands/basilica-of-the-annunciation/ | core + story + associated saint. **Missing: account_*, primary_references, image** | none |
| Basilica of the Nativity (Bethlehem) | 1129 (same) | basilica-of-the-nativity | live | /explore/holy-lands/basilica-of-the-nativity/ | same as Annunciation | none |

Other Holy Land pages (all live, all with coordinates, none with an image; same IDs in both DBs):
Capernaum 1133 · Church of All Nations (Gethsemane) 1131 · Church of the Multiplication (Tabgha) 1200 ·
Pater Noster 1194 · Transfiguration (Mount Tabor) 1193 · Visitation (Ein Karem) 1195 ·
Dormition Abbey 1201 · Mount of Beatitudes 1132 · Qasr el-Yahud 1196 · Stella Maris 1198 ·
The Cenacle 1134 · Tomb of Lazarus 1199 · Via Dolorosa 1135 · Wedding Church of Cana 1197.

### The 21 Alta California missions

Matched by name and founding year to your list, then checked against California State Parks
(parks.ca.gov/?page_id=22679). **Founding order and years agree in all three sources** (your list, State
Parks, our DB). Name differences on the State Parks page: #14 "San José **de Guadalupe**" (DB:
"Mission San José"); #21 "San Francisco **de** Solano" (DB: "San Francisco Solano"); #2 is misspelled
there ("Calros Borremeo"); #11 has no accent ("Purisima"). State Parks gives years only, not dates.

All 21: page exists **Y**, model `catalog.SacredSitePage` (category "Shrine & Basilica"), live in both
DBs, latitude/longitude present, founding date present in `date_display`, member of the Mission Trail.

| # | mission | prod id | local id | date_display | prod image | trail stop (S→N) |
|---|---|---|---|---|---|---|
| 1 | San Diego de Alcalá | 1310 | 1357 | July 16, 1769 | img#32 | 0 |
| 2 | San Carlos Borromeo de Carmelo | 1311 | 1358 | June 3, 1770 | — | 13 |
| 3 | San Antonio de Padua | 1312 | 1359 | July 14, 1771 | — | 11 |
| 4 | San Gabriel Arcángel | 1313 | 1360 | Sept 8, 1771 | img#35 | 3 |
| 5 | San Luis Obispo de Tolosa | 1314 | 1361 | Sept 1, 1772 | — | 9 |
| 6 | San Francisco de Asís (Dolores) | 1315 | 1362 | Oct 9, 1776 ⚠ | — | 18 |
| 7 | San Juan Capistrano | 1218 | 1218 | "Founded 1776" (year only) | img#34 | 2 |
| 8 | Santa Clara de Asís | 1316 | 1363 | Jan 12, 1777 | — | 16 |
| 9 | San Buenaventura | 1317 | 1364 | Mar 31, 1782 | — | 5 |
| 10 | Santa Bárbara | 1318 | 1365 | Dec 4, 1786 | — | 6 |
| 11 | La Purísima Concepción | 1319 | 1366 | Dec 8, 1787 | — | 8 |
| 12 | Santa Cruz | 1320 | 1367 | Aug 28, 1791 | — | 15 |
| 13 | Nuestra Señora de la Soledad | 1321 | 1368 | Oct 9, 1791 | — | 12 |
| 14 | San José | 1322 | 1369 | June 11, 1797 | — | 17 |
| 15 | San Juan Bautista | 1323 | 1370 | June 24, 1797 | — | 14 |
| 16 | San Miguel Arcángel | 1324 | 1371 | July 25, 1797 | — | 10 |
| 17 | San Fernando Rey de España | 1325 | 1372 | Sept 8, 1797 | — | 4 |
| 18 | San Luis Rey de Francia | 1326 | 1373 | June 13, 1798 | img#33 | 1 |
| 19 | Santa Inés | 1327 | 1374 | Sept 17, 1804 | — | 7 |
| 20 | San Rafael Arcángel | 1328 | 1375 | Dec 14, 1817 | — | 19 |
| 21 | San Francisco Solano | 1329 | 1376 | July 4, 1823 | — | 20 |

Flags (report only, nothing changed):

- ⚠ #6 Mission Dolores: `date_display` says October 9, 1776. Many sources give the founding as late
  June 1776 and October 9 as the formal dedication. **Verify against a primary source before
  any child page uses the date.** State Parks gives only the year, so it can't settle this.
- #7 San Juan Capistrano has year only; a full date needs a source.
- **Duplicate older pages** (both live): 1144 "Mission Basilica San Diego de Alcala" (Shrine & Basilica)
  and 1126 "Carmel Mission Basilica (St. Junipero Serra)" (Saints & Tombs) duplicate #1 and #2.
  Their coordinates differ slightly from the trail pages. Future Saints should link only to the trail pages.
- Only 4 of 21 missions have an image in production, and none has a credit field.

### Missing, per Phase 2 seed page

| seed | missing for a child page (canonical side) | editorial layer needed (all new) |
|---|---|---|
| St. Carlo Acutis | `portrait_credit` (the portrait can't be shown without it); `source_url`; absent from the local DB | both stories, Quick Facts "known for", timeline, fun facts, words, Think About It, 5 quiz Qs, sources, child portrait illustration |
| Our Lady of Lourdes | an image credit (featured_image has no credit field) | all editorial fields; child wording of Church status |
| Eucharistic Miracle of Lanciano | `recognition_year`, `primary_references`, image credit | all editorial; careful "what was reported" vs. scientific-claim wording (brief §4) |
| Church of the Holy Sepulchre | `primary_references`, image | all editorial + Bible citations, history vs. tradition |
| Mission San Diego de Alcalá | `primary_references`, image credit; no founding-number or Native-community field anywhere | all editorial + founding #, Native peoples section (community named from cited sources), Build This Mission (Phase 3) |

### Missing, per mission (all 21)

Canonical side: founding number (no field; Phase 3 adds `founding_number` on the mission companion,
verified against State Parks); image credit for all 21 (17 have no image at all); `primary_references` empty on
the audited San Diego page (expect the same on the others; to be confirmed per page in Phase 3).
Editorial side for every mission: Indigenous community name(s) with source support, child stories at
both levels, timeline, quiz, Build This Mission project, licensed art.

### Phase 3 checklist (owner note, 2026-11-05)

- The Future Saints mission companion gets structured `founding_number`, `founding_date` (+ display
  text) and a source note. The adult mission pages are not changed.
- The Mission Trail's stop order is south → north geography, **not** founding order. Never use it as such.
- **Mission Dolores (#6):** the canonical date is October 9, 1776, which may be the dedication rather than
  the founding. Resolve from a primary source before any child page shows a date.
- **San Juan Capistrano (#7):** the canonical date is year only ("Founded 1776"). Find a sourced full
  date or show the year only.
- **Duplicates:** 1144 "Mission Basilica San Diego de Alcala" and 1126 "Carmel Mission Basilica (St.
  Junipero Serra)". Link companions to the current trail pages (production 1310 and 1311; look them up
  by slug `mission-san-diego-de-alcala` / `mission-san-carlos-borromeo-de-carmelo`), never to these.
