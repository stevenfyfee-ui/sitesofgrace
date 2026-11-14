# Future Saints: affiliate and privacy gates (Phase 0)

This is an engineering inventory, not a legal opinion. **Nothing here claims COPPA compliance.**
Items marked COUNSEL need a lawyer's sign-off before the switch goes to "on".

## 1. What the adult base.html brings with it (A3)

Main template: `sitesofgrace/templates/base.html`. Header and footer are inline. Includes:
`includes/_search_bar.html` (×2), `includes/_account_menu.html` (signed-in only; pulls
`_line_icon.html` and `planner_tags`), `menus/main_menu.html`, `sub_menu.html`, `mobile_menu.html`,
`mobile_sub_menu.html`, `footer_menu.html`; tags from `pilgrim_tags`, `support_tags`, `legal_tags`,
`about_tags`, `blog_tags`, `v2_tags`, `destination_tags`. CSS: `css/site.css`, `css/search.css`. JS:
inline menu toggle, `js/search.js`, `js/account-menu.js` (signed-in only).

### External hosts

| host | where | Future Saints |
|---|---|---|
| fonts.googleapis.com (stylesheet + preconnect) | base.html:10, 12 | **DROP**: third-party request that exposes the child's IP. Replaced by self-hosted Lora. |
| fonts.gstatic.com (preconnect + font files) | base.html:11 | **DROP** (same reason) |
| Social profile hosts (admin-entered URLs) | base.html:73-78 | **DROP**: no social widgets or links on child routes |
| Admin-entered menu links (may be external) | main/footer menus | **DROP**: the Future Saints nav is fixed and internal |
| tp-em.com (Travelpayouts) | **not present** in base.html, its includes, or any app code. It appears only in the package's prompt file. | n/a. The banned-string test keeps it out. |
| Esri tiles, Google APIs, "Today in the Church" | adult home_page.html / `_today_in_church.html` only, **not base** | never included |
| Leaflet | self-hosted, map pages only | not used (brief §8) |

### Cookies and storage

| item | set by | anonymous visitor? | Future Saints |
|---|---|---|---|
| `csrftoken` | bare `{% csrf_token %}` at base.html:19, plus newsletter and sign-out forms | **yes, on every adult page** | **DROP**: Future Saints base has no csrf_token and no POST forms, so no cookie. Tested. |
| `sessionid` | session writes in home/models.py:2177, tours/views.py:53, allauth login | no (only on those actions) | none. Future Saints never writes the session. |
| `messages` | messages middleware, only when a message is queued | no | none |
| localStorage `LEGEND_KEY` | map_page.html only | n/a | not included |
| sessionStorage `fs-reading-level` | removed in Phase 2a (one reading level for grades 2–5) | n/a | Future Saints now uses no cookies and no browser storage. |

Note for SOC 2 records: the site-wide `csrftoken` on anonymous adult pages is pre-existing and
unchanged by this work. It's a functional cookie, but the Cookies & Tracking Notice (draft, prod
id 2510) should describe it.

### UI blocks

| block | where | Future Saints | why |
|---|---|---|---|
| Logo/wordmark | base:27-33 | **KEEP**, reused via `SiteSettings.logo` | brand |
| Main nav (wagtailmenus + Blog / Our Story) | base:37 | **REPLACE** with the fixed Future Saints section nav plus a "← Sites of Grace" link | adult nav leads to travel/planner/store |
| Search bar + type-ahead (`search.js`) | base:41, 53 | **DROP** | results include adult and travel pages |
| Account menu (Passport, Photos, My Trips, Feed, Notifications) | base:44-56 | **DROP** | accounts, user content, planner |
| "Sign in" / Pilgrim Portal | base:46 | **DROP** | no sign-in on child routes |
| Mobile menu toggle | base:48-57 | **REPLACE** with an accessible disclosure | |
| Social links | base:73-78 | **DROP** | |
| Footer menus Explore / Learn & About | base:86-93 | **DROP** | adult destinations |
| Support Sites of Grace (donate) | base:99-104 | **DROP** | no donations |
| Legal & Policies links | base:110-117 | **REPLACE** with "A note for grown-ups" → Privacy Policy (staff-only warning chip while it's not live) | |
| Newsletter "Stay Inspired" email form | base:120-136 | **DROP** | email collection from children |
| Independence disclaimer / copyright / Accessibility | base:141-143 | **KEEP** the Church-status disclaimer line, copyright, and "Back to Sites of Grace" | |
| Skip link | base:21 | **KEEP** (copied markup) | |
| Shop/store, Today in the Church, booking/planner CTAs | not in base | never added | |

## 2. What the Future Saints base removes

The separate `templates/future_saints/base.html` has: no external host of any kind; no
`{% csrf_token %}`; no forms except the GET reading-level control (which works as plain links
without JS) and the GET search box; no adult site search (Future Saints has its own kids-safe
search of published Future Saints pages only: `docs/future-saints/search.md`); no account, sign-in, newsletter, donate, store, social, comments,
analytics, ads, geolocation, or iframes; self-hosted Lora; same-origin CSS/JS only. A test renders
every Future Saints page and fails if any of these appear: `tp-em.com`, `fonts.googleapis`,
`fonts.gstatic`, `esri`, `amazon.`, `amzn`, `affiliate`, `booking`, `/plan/`, `newsletter`,
`sign in`, `sign up`, `donate`, `csrfmiddlewaretoken`, `http://` / `https://` to any non-site host.

## 3. Amazon Associates: child-directed gate (BLOCKED)

Per brief §7: Amazon's Associates participation requirements list sites "directed toward children"
as unsuitable, and Future Saints is child-directed. **No affiliate link, Amazon tag, product widget,
merchant logo, "buy" prompt or shopping CTA anywhere under `/future-saints/`, including print views
and mission materials lists.** Materials lists are plain editorial text.

The gate stays closed until **all three** exist in writing:

1. Written clarification from Amazon Associates on whether a separately governed adult
   Parent & Teacher page on the same domain keeps the account eligible.
2. Counsel's review of that answer plus FTC/COPPA implications. COUNSEL.
3. Owner approval recorded in the PR or change ticket (SOC 2 change-management evidence).

Engineering safeguards: the banned-string test above; no model field for a URL on any materials
or step row; the Affiliate Disclosure page (draft, prod id 2504) is never linked from Future Saints.

Also open: if the adult site carries Amazon Associates links (not verified in this audit), and Amazon
treats eligibility site-wide, launching a child section on sitesofgrace.com could affect the adult
account too. Raise this in the Amazon
inquiry (item 1). COUNSEL.

## 4. COPPA pre-launch checklist (to do; nothing here is done or claimed)

Personal information and identifiers
- [ ] Confirm that anonymous Future Saints responses set no cookies (automated test, Phase 1).
- [ ] Confirm no persistent identifiers: no analytics, no fingerprinting, no third-party requests (test + manual network-panel check at launch).
- [x] ~~Decide whether the `fs-reading-level` sessionStorage value is acceptable.~~ Moot: removed in Phase 2a; Future Saints uses no browser storage.
- [ ] Confirm server logs: what request data (IP, user agent) App Platform and the CDN keep, for how long, and whether it's used for anything beyond operations. Document in the privacy note. COUNSEL on the "support for internal operations" exception.
- [ ] Confirm no data collection: no forms, uploads, accounts, comments, quiz-score storage, or email.

Third parties
- [ ] Inventory every host a Future Saints page contacts (target: same origin + the media CDN only).
- [ ] Media CDN (DigitalOcean Spaces): confirm no access logging tied to individuals, or document it.

Notice
- [ ] Publish the site Privacy Policy (currently **draft**, prod id 2502; absent locally).
- [ ] Write a "note for grown-ups" for the children's section: what's collected (nothing beyond
      server logs), cookies (none), third parties (none), contact for parents. COUNSEL to draft or approve.
- [ ] Link it from every Future Saints page footer (Phase 1 builds the link and the not-live warning).

Content and links
- [ ] No outbound links to commercial or social destinations.
- [ ] Decide how source links to Vatican/USCCB/State Parks/museum sites are shown to children (for
      example, a visible "this link leaves Sites of Grace" label). COUNSEL.
- [ ] Human editorial review recorded through the Wagtail workflow before anything is published.

Launch
- [ ] Owner approval to change `SOG_FUTURE_SAINTS` from "staff" to "on" (env var change = change
      ticket; not done by Claude).
- [ ] Re-run the banned-string, cookie and adult-regression tests against the deployed build.

HIPAA: not applicable. Future Saints handles no patient data. Nothing here touches the BAA scope.
