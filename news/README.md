# Scheduling `fetch_news`

`python manage.py fetch_news` fetches all enabled `NewsSource` feeds and upserts
`NewsItem` rows. It does not run on a request path -- something outside Django
must invoke it on a schedule. This repo doesn't yet have a fixed hosting
platform checked in (no CI/CD, k8s manifests, or PaaS config), so pick whichever
of these matches wherever this app actually runs and drop the others.

Run daily, off-peak, from the project root with the venv active.

## Linux server with cron

```
0 3 * * * cd /path/to/sitesofgrace && /path/to/venv/bin/python manage.py fetch_news >> /var/log/sitesofgrace/fetch_news.log 2>&1
```

## systemd timer

`/etc/systemd/system/sitesofgrace-fetch-news.service`:
```ini
[Unit]
Description=Sites of Grace: fetch_news

[Service]
Type=oneshot
User=wagtail
WorkingDirectory=/path/to/sitesofgrace
ExecStart=/path/to/venv/bin/python manage.py fetch_news
```

`/etc/systemd/system/sitesofgrace-fetch-news.timer`:
```ini
[Unit]
Description=Run Sites of Grace fetch_news daily

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with `systemctl enable --now sitesofgrace-fetch-news.timer`.

## Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: sitesofgrace-fetch-news
spec:
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: fetch-news
              image: <same image tag deployed for the web service>
              command: ["python", "manage.py", "fetch_news"]
              envFrom:
                - secretRef:
                    name: sitesofgrace-env
          restartPolicy: Never
```

## Docker Compose (VM-hosted)

Add a sidecar service using the same image, overriding the command; a
lightweight scheduler container (e.g. `docker/compose` with `ofelia`, or just
cron installed in a small image) triggers `docker compose run --rm web python
manage.py fetch_news` daily. Wire this into whatever compose file actually
deploys the app in production -- not the local `docker-compose.yml` here,
which only runs Postgres for development.

## Local Windows dev machine (Task Scheduler)

For testing the schedule locally, not for production:

```
schtasks /Create /SC DAILY /ST 03:00 /TN "SitesOfGrace fetch_news" ^
  /TR "C:\Users\stevenf\sitesofgrace\venv\Scripts\python.exe C:\Users\stevenf\sitesofgrace\manage.py fetch_news" ^
  /RU "%USERNAME%"
```

Whichever mechanism is used, make sure `DJANGO_SETTINGS_MODULE` resolves to the
correct settings module for that environment (`manage.py` defaults to
`sitesofgrace.settings.dev`) and that the process has database access.
