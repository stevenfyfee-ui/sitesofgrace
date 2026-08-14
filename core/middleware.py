import base64
import binascii
import logging
import secrets

from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)


class SitePrivateMiddleware:
    """Gate the whole site behind HTTP Basic Auth when SITE_PRIVATE is on.

    Fails closed: any missing/malformed credential, header, or config is
    treated as unauthorized rather than allowed through.
    """

    # Exact match, no trailing-slash normalization (this middleware runs
    # before CommonMiddleware's APPEND_SLASH). .do/app.yaml's health check
    # path must be exactly "/health/" or the deploy will never go healthy.
    # Keep in sync with SECURE_REDIRECT_EXEMPT in settings/production.py.
    HEALTH_CHECK_PATH = "/health/"

    # Realm must stay pure ASCII: Django encodes header values as latin-1
    # and MIME-encodes anything outside that range, which mangles the
    # leading "Basic " token and leaves browsers unable to parse this as an
    # auth challenge at all.
    WWW_AUTHENTICATE = 'Basic realm="Sites of Grace private preview", charset="UTF-8"'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "SITE_PRIVATE", False):
            return self.get_response(request)

        response = self._handle(request)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def _handle(self, request):
        if request.path == self.HEALTH_CHECK_PATH:
            return self.get_response(request)

        expected_user = getattr(settings, "SITE_PRIVATE_USER", "")
        expected_password = getattr(settings, "SITE_PRIVATE_PASSWORD", "")
        if not expected_user or not expected_password:
            logger.error(
                "SITE_PRIVATE is active but SITE_PRIVATE_USER/SITE_PRIVATE_PASSWORD "
                "is not fully configured; denying all requests."
            )
            return self._unauthorized()

        credentials = self._parse_credentials(request)
        if credentials is None:
            return self._unauthorized()

        username, password = credentials
        username_ok = secrets.compare_digest(
            username.encode("utf-8"), expected_user.encode("utf-8")
        )
        password_ok = secrets.compare_digest(
            password.encode("utf-8"), expected_password.encode("utf-8")
        )
        if not (username_ok & password_ok):
            return self._unauthorized()

        return self.get_response(request)

    @staticmethod
    def _parse_credentials(request):
        header = request.META.get("HTTP_AUTHORIZATION")
        if not header or " " not in header:
            return None

        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic":
            return None

        try:
            decoded_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return None

        try:
            decoded = decoded_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return None

        if ":" not in decoded:
            return None

        username, password = decoded.split(":", 1)
        return username, password

    def _unauthorized(self):
        response = HttpResponse("Authentication required", status=401, content_type="text/plain")
        response["WWW-Authenticate"] = self.WWW_AUTHENTICATE
        return response
