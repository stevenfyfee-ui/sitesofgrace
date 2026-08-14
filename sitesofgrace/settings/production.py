"""
Production settings for sitesofgrace project — DigitalOcean App Platform.

Everything that differs from `base.py` is sourced from the environment.
No secrets live in this file or anywhere else in the repo. There is no
`.local` override hook here (unlike dev.py) — production behavior must not
depend on an untracked file.

BUILD-TIME CONSTRAINT: `collectstatic` runs during the App Platform *build*
step, before the app's *runtime* environment variables (notably
DATABASE_URL) are available. This module must therefore import cleanly, and
`manage.py collectstatic` must succeed, even with DATABASE_URL unset. Only a
missing SECRET_KEY/DATABASE_URL at genuine runtime is a hard failure.
"""

import logging
import os
import re
import sys

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


def _truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes"}


def _csv_env(name):
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


# Whether the current management command is `collectstatic`. Used below to
# allow the process to start with no SECRET_KEY / no DATABASE_URL at build
# time, without weakening the runtime requirement.
_RUNNING_COLLECTSTATIC = "collectstatic" in sys.argv


# --- Core -----------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if _RUNNING_COLLECTSTATIC:
        # collectstatic never signs anything or touches session/CSRF secrets;
        # this value is never used to serve a request.
        SECRET_KEY = "build-time-placeholder-not-used-at-runtime"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable is required in production."
        )

DEBUG = False

ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS")

CSRF_TRUSTED_ORIGINS = [
    origin if "://" in origin else f"https://{origin}"
    for origin in _csv_env("CSRF_TRUSTED_ORIGINS")
]

WAGTAILADMIN_BASE_URL = os.environ.get("WAGTAILADMIN_BASE_URL", "")


# --- Database -------------------------------------------------------------
# DATABASE_URL is not present during the App Platform build (see module
# docstring), so the dummy, connection-free fallback below is scoped strictly
# to `collectstatic`. Any other runtime path with no DATABASE_URL fails hard
# rather than silently booting against an empty in-memory database.

_DATABASE_URL = os.environ.get("DATABASE_URL")
if _DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            _DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
elif _RUNNING_COLLECTSTATIC:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    raise ImproperlyConfigured(
        "DATABASE_URL environment variable is required in production."
    )


# --- Security / HTTPS ------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Left low deliberately while the site is still private / pre-launch, so a
# misconfiguration doesn't lock out browsers for a long time. Raise this
# (e.g. to 31536000, with SECURE_HSTS_PRELOAD) once the domain is stable and
# you're ready to go public — see DEPLOY.md "Going public".
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

X_FRAME_OPTIONS = "DENY"

# The health check must not be forced through the HTTPS redirect: App
# Platform's rollout prober hits it over plain HTTP. Django matches these
# patterns against request.path with the leading slash stripped. Derived
# from HEALTH_CHECK_PATH (base.py) rather than hardcoded, so this can't
# drift from core.middleware.HealthCheckMiddleware/SitePrivateMiddleware.
SECURE_REDIRECT_EXEMPT = [r"^" + re.escape(HEALTH_CHECK_PATH.lstrip("/")) + r"$"]


# --- Site-wide privacy (HTTP Basic Auth) -----------------------------------
# See core/middleware.py:SitePrivateMiddleware, which reads these back via
# django.conf.settings (not os.environ directly) so there's one source of
# truth and tests can drive it with override_settings. Truthy env values:
# 1/true/yes (case-insensitive). Leave SITE_PRIVATE unset/false to go public.

SITE_PRIVATE = _truthy(os.environ.get("SITE_PRIVATE", ""))
SITE_PRIVATE_USER = os.environ.get("SITE_PRIVATE_USER", "")
SITE_PRIVATE_PASSWORD = os.environ.get("SITE_PRIVATE_PASSWORD", "")

# Separate from SITE_PRIVATE on purpose: crawler exposure and access control
# are different concerns (e.g. switching to Wagtail-native page privacy
# while SITE_PRIVATE stays unset). See core/middleware.py:NoindexMiddleware
# and core/views.py:robots_txt.
SITE_NOINDEX = _truthy(os.environ.get("SITE_NOINDEX", ""))


# --- Static & media storage -----------------------------------------------
# Media MUST live on Spaces: the App Platform filesystem is ephemeral, so
# anything editors upload to local disk is destroyed on the next deploy.

SPACES_BUCKET = os.environ.get("SPACES_BUCKET", "")
if not SPACES_BUCKET and not _RUNNING_COLLECTSTATIC:
    # collectstatic never touches the "default" (media) storage, so don't
    # warn during the build — only once the app is actually about to run
    # and would silently be writing editor uploads to a throwaway disk.
    logger.warning(
        "SPACES_BUCKET is not set. Media uploads have no durable storage "
        "configured and will be written to the container's local, "
        "EPHEMERAL filesystem — they will be LOST on the next deploy."
    )

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.environ.get("SPACES_KEY", ""),
            "secret_key": os.environ.get("SPACES_SECRET", ""),
            "bucket_name": SPACES_BUCKET,
            "region_name": os.environ.get("SPACES_REGION", ""),
            "endpoint_url": os.environ.get("SPACES_ENDPOINT_URL", ""),
            "custom_domain": os.environ.get("SPACES_CDN_DOMAIN") or None,
            "default_acl": "public-read",
            "querystring_auth": False,
            "file_overwrite": False,
            "object_parameters": {
                "CacheControl": "max-age=31536000, public",
            },
        },
    },
    # CompressedManifestStaticFilesStorage gives hashed, immutable filenames
    # so a Wagtail upgrade can't leave browsers serving stale CSS/JS from
    # cache. This intentionally replaces the base STORAGES dict wholesale.
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# --- Middleware -----------------------------------------------------------
# Insert, in order, right after SecurityMiddleware:
#   1. SitePrivateMiddleware — must run BEFORE WhiteNoise. WhiteNoise's
#      process_request() serves static files directly and short-circuits the
#      response, so if it ran first, static assets would be served
#      unauthenticated while the site is private.
#   2. WhiteNoiseMiddleware — serves static files straight from the app
#      process.
# Located by name (rather than assumed index) so a reordering of base
# MIDDLEWARE can't silently drop either middleware.

MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405

try:
    _security_index = MIDDLEWARE.index(
        "django.middleware.security.SecurityMiddleware"
    )
except ValueError:
    raise ImproperlyConfigured(
        "django.middleware.security.SecurityMiddleware was not found in the base "
        "MIDDLEWARE list; cannot insert SitePrivateMiddleware/WhiteNoiseMiddleware "
        "after it."
    )

MIDDLEWARE[_security_index + 1 : _security_index + 1] = [
    "core.middleware.SitePrivateMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
]

# HealthCheckMiddleware must be the absolute first entry: it has to run
# before SecurityMiddleware/CommonMiddleware ever call anything that
# triggers ALLOWED_HOSTS validation (see its docstring). NoindexMiddleware
# comes right after so it wraps every real response — including
# SitePrivateMiddleware's 401s — but not the health check's short-circuit,
# which doesn't need an X-Robots-Tag header.
MIDDLEWARE = [
    "core.middleware.HealthCheckMiddleware",
    "core.middleware.NoindexMiddleware",
] + MIDDLEWARE
