# Deploying sitesofgrace to DigitalOcean App Platform

This project deploys as a single Docker image (`Dockerfile`) via the App
Platform spec in `.do/app.yaml`: one `web` service, one `PRE_DEPLOY` job
that runs migrations, and one managed Postgres database component.

## Environment variables

All of these are declared (as placeholders) in `.do/app.yaml`. Fill in real
values there, or override per-environment in the App Platform console under
your app → Settings → your component → Environment Variables.

| Variable | Example value | Secret? | Build/Run time |
|---|---|---|---|
| `SECRET_KEY` | `<48+ random bytes, base64>` | Yes | Run-time (collectstatic tolerates it missing at build — see `settings/production.py` docstring) |
| `DATABASE_URL` | *(bound automatically from the `sitesofgrace-db` component)* | Yes — it's a full connection string with a password | Run-time only |
| `ALLOWED_HOSTS` | `${APP_DOMAIN}` | No | Run-time |
| `CSRF_TRUSTED_ORIGINS` | `${APP_DOMAIN}` | No | Run-time |
| `WAGTAILADMIN_BASE_URL` | `https://${APP_DOMAIN}` | No | Run-time |
| `SITE_PRIVATE` | `true` | No | Run-time |
| `SITE_PRIVATE_USER` | `preview` | Yes | Run-time |
| `SITE_PRIVATE_PASSWORD` | `<random>` | Yes | Run-time |
| `SPACES_KEY` | `DO00...` | Yes | Run-time |
| `SPACES_SECRET` | `<random>` | Yes | Run-time |
| `SPACES_BUCKET` | `sitesofgrace-media` | No | Run-time |
| `SPACES_REGION` | `nyc3` | No | Run-time |
| `SPACES_ENDPOINT_URL` | `https://nyc3.digitaloceanspaces.com` | No | Run-time |
| `SPACES_CDN_DOMAIN` | `` *(blank, or a CDN domain fronting Spaces)* | No | Run-time |
| `DJANGO_SETTINGS_MODULE` | `sitesofgrace.settings.production` | No | Build **and** run — set as an `ENV` in the `Dockerfile` itself, not in `app.yaml`. Required so `manage.py`/`wsgi.py`'s `os.environ.setdefault(..., "sitesofgrace.settings.dev")` fallback never wins. |

`DATABASE_URL` and `SECRET_KEY` are the two settings that hard-fail the app
at real runtime if missing (`ImproperlyConfigured`) — everything else has a
safe fallback or just logs a warning (`SPACES_BUCKET` unset, for instance).

Local dev (`sitesofgrace.settings.dev`) is unaffected by any of this — it
uses `DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT` from `base.py`,
which is a separate set of variables with local-only defaults.

## Creating the first superuser

The `PRE_DEPLOY` migrate job runs automatically on every deploy, but nothing
creates a Django superuser for you. After the first successful deploy:

1. App Platform dashboard → your app → the `web` component → **Console** tab.
2. This opens an interactive shell in a running instance. Run:
   ```
   python manage.py createsuperuser
   ```
3. Follow the prompts (email, password).

(There's also a `doctl apps console <app-id> --component web` CLI path if
you prefer that — check `doctl apps console --help` for the current syntax,
since DO has changed subcommand names before and I haven't verified this
one against a live account.)

## Launch-day checklist (going from private preview to public)

1. **Turn off the privacy gate.** Set `SITE_PRIVATE` to `false` (or delete
   the env var) on the `web` component and redeploy. `core/middleware.py`'s
   `SitePrivateMiddleware` becomes a no-op immediately.
2. **Raise HSTS duration.** In `sitesofgrace/settings/production.py`, change
   `SECURE_HSTS_SECONDS = 3600` to `SECURE_HSTS_SECONDS = 31536000` (1 year).
   This is a code change — commit and redeploy.
3. **Add HSTS preload.** In the same block, add
   `SECURE_HSTS_PRELOAD = True`. Do this in the *same* deploy as step 2, not
   before — preload asks browsers to hardcode HTTPS-only for your domain
   before you've proven a year of clean HTTPS service, which is what step 2
   establishes. After this ships and has been live for a while, submit the
   domain at https://hstspreload.org if you want it in browser preload
   lists — that submission is manual and outside this repo.
4. **Point the domain.** App Platform dashboard → your app → **Settings** →
   **Domains** → add your custom domain, then update your DNS per DO's
   instructions. Confirm `${APP_DOMAIN}` resolves to the custom domain once
   it's set as primary — if it doesn't, add the custom domain explicitly to
   `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (both are comma-separated env
   vars, so you can list more than one host).
5. **Robots block drops on its own.** `core/views.py`'s `robots_txt` view
   already reads `settings.SITE_PRIVATE` at request time — once step 1 is
   done, `/robots.txt` automatically switches from `Disallow: /` to
   `Allow: /` plus a `Sitemap:` line. Verify with `curl https://<domain>/robots.txt`
   after redeploying.
6. **Submit the sitemap.** ⚠️ There is currently **no sitemap wired up in
   this repo** — `/robots.txt` points at `/sitemap.xml`, but that URL 404s
   today. Add `wagtail.contrib.sitemaps` (or `django.contrib.sitemaps`) and
   a `path("sitemap.xml", ...)` route before this step is meaningful, then
   submit the sitemap URL in Google Search Console / Bing Webmaster Tools.

## Rolling back a bad deploy

1. App Platform dashboard → your app → **Activity** (or **Deployments**)
   tab → find the last known-good deployment → **Rollback to this
   deployment**.
2. This reverts the running container image, but it does **not** reverse
   any database migration that ran in the bad deploy's `PRE_DEPLOY` job —
   migrations aren't transactional across a rollback. If the bad deploy
   included a schema change, rolling back the app alone can leave the
   database ahead of the code. Check `python manage.py showmigrations`
   against the restored code and write/run a reverse migration by hand if
   needed before treating the rollback as complete.
3. If the bad deploy already ran destructive data changes (not just schema),
   a rollback doesn't undo those either — that needs a database restore
   from a DO-managed Postgres backup/snapshot, which is a separate,
   heavier operation than an app rollback.

## Instance sizing

`.do/app.yaml` currently sets `instance_size_slug: apps-s-1vcpu-1gb` on both
the `web` service and the `migrate` job. That's DigitalOcean's **Standard**
tier at 1 vCPU / 1 GiB — **$12/mo** per component as of when this was
written. You mentioned a cheaper **$10/mo "Fixed" 1 GiB** tier also exists;
I don't have a confirmed slug string for it from here (DO has renamed these
before), so I didn't guess one into `app.yaml`. Check
`doctl apps tier instance-size list` or the App Platform pricing page for
the exact slug, then swap `instance_size_slug` on the `web` service (and
independently on the `migrate` job, if you want it smaller — a migration
job doesn't need the same headroom as the always-on web service).
