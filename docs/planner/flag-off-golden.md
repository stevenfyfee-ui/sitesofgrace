# Flag-off byte-identical test: regenerating the saved copies

`planner/tests/test_flag_off.py` proves that with `SOG_PLANNER_V2=off`, `/plan/` renders exactly as it
does on `main` without Trip Planner v2. It compares four renders against saved copies in
`planner/tests/golden/`:

- signed out
- `?site=`
- signed in with journey picks
- the rest of v2 switched on

Before comparing, both sides get the CSRF token and any hashed static filename (`site.124697dd488a.css`)
replaced with a placeholder.

## When to regenerate

Only when `main` changes markup that `/plan/` shares, such as `base.html`, the header, the footer or
the account menu, and the test then fails on `planner-v2` after merging `main`. A change to a CSS or JS
file alone doesn't need it.

## How

Always render from **`origin/main`**, never from `planner-v2`. The copies must show what `main` renders
with no planner v2 code at all, so rendering from the branch would only prove the branch matches itself.

```bash
git fetch origin
git worktree add --detach ../sog-main-golden origin/main
cp sitesofgrace/settings/local.py ../sog-main-golden/sitesofgrace/settings/local.py   # DB credentials (gitignored)
rm ../sog-main-golden/planner/tests.py                                              # main still has the stub module
mkdir -p ../sog-main-golden/planner/tests
: > ../sog-main-golden/planner/tests/__init__.py
cp planner/tests/test_flag_off.py ../sog-main-golden/planner/tests/
cd ../sog-main-golden
PLANNER_WRITE_GOLDEN=1 ../sitesofgrace/venv/Scripts/python.exe manage.py test planner.tests.test_flag_off
cd ../sitesofgrace
cp ../sog-main-golden/planner/tests/golden/*.html planner/tests/golden/
git worktree remove --force ../sog-main-golden
git diff planner/tests/golden/      # the only changes should be the ones main made on purpose
venv/Scripts/python.exe manage.py test planner.tests.test_flag_off
```

Stop the full test suite before you start, because both runs use the same test database.

## After Trip Planner v2 is merged

`main` then contains the planner v2 code, so `origin/main` is no longer a v2-free reference. Regenerate
only for a deliberate shared-layout change. Render from `main` with `SOG_PLANNER_V2=off`, and check that
`git diff planner/tests/golden/` shows that change and nothing else. Once the flag and the old estimator
are removed, delete this test and its copies.
