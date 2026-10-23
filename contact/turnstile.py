"""
Cloudflare Turnstile for the contact form -- off unless both
TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY are set. While it's off, no
widget renders and nothing is sent to Cloudflare.

Turnstile is a standalone Cloudflare service; it doesn't need the domain's
DNS on Cloudflare.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT_SECONDS = 5


def enabled():
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


def verify(token):
    """True if Cloudflare accepts the widget's token. Any network failure
    counts as a failed check. The visitor's IP is not sent."""
    if not token:
        return False
    data = urllib.parse.urlencode({
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token[:2048],
    }).encode()
    try:
        with urllib.request.urlopen(VERIFY_URL, data=data, timeout=TIMEOUT_SECONDS) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        logger.warning("Turnstile verification request failed.", exc_info=True)
        return False
    return bool(result.get("success"))
