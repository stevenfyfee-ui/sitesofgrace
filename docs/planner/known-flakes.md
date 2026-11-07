# Known test flakes seen during Trip Planner v2

## home.tests.HomeTests (site root path cache)

- **Tests:** `home.tests.HomeTests.test_homepage_is_renderable` and
  `home.tests.HomeTests.test_homepage_template_used`
- **Seen in:** the full-suite run before the Phase 2 commit on `planner-v2`, on 2026-11-03: 731 tests,
  3 failures and 1 error. Both tests got a 404 for `self.homepage.url`; the response was rendered with
  `404.html`.
- **Didn't come back:**
  - `manage.py test home.tests.HomeTests` alone passed.
  - The apps that run before it, run together with it (`blog catalog contact core destinations
    home.tests`, 280 tests), passed.
  - The next full suite, run verbose with nothing else running, passed both: 735 tests, with only the
    two environment failures below.
- **Likely cause:** the same isolation problem the v2 build notes record as follow-up 15. Wagtail caches
  site root paths process-wide, and `HomeTests.setUp` adds a second default `Site` without clearing that
  cache, so a stale entry can send `page.url` to the wrong root. It isn't caused by planner code. No planner
  test runs before `home` in the suite order, and the planner tests clear the cache in their own `setUp`.
- **Fix later (not in this branch):** call `Site.clear_site_root_paths_cache()` in `HomeTests.setUp`, as
  `catalog/tests_v2_site.py` already does.

## Environment failures on this laptop (not flakes; they fail on main too)

- `home.tests_v2_golive.LegalCommandsTests.test_set_legal_details_refuses_without_a_prompt`: the shell
  here gives the test a stdin, and the test expects none (`EOFError`).
- `pilgrims.tests.test_storage.RealSettingsConfigTests.test_pilgrim_private_options`: expects the Spaces
  region env var (`sfo3`), which isn't set locally.

## Known gap: v1 planner journey order

- The v1 planner (`planner/models.py`, served only with `SOG_PLANNER_V2` off) has the same unordered `SiteVisit` query that #20 fixed in v2; fix it (`order_by("created_at", "pk")`) or remove it whenever v1 is retired.
