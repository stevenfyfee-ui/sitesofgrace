"""Local development inside Docker (docker-compose.dev.yml). Never used in
production: the Dockerfile pins settings.production and App Platform never
sets DJANGO_SETTINGS_MODULE to this module.

dev.py pulls in the gitignored local.py, whose DATABASES points at
127.0.0.1 -- the Windows host's view of Postgres. Inside the web container
the database is the compose "db" service, so DATABASE_URL wins here.
"""
import os

import dj_database_url

from .dev import *  # noqa: F401,F403

if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"])}
