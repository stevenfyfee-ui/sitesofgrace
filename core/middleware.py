import base64
import binascii
import logging
import secrets

from django.conf import settings
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)


class HealthCheckMiddleware:
    """Answer the platform's health probe before anything else can reject it.

    App Platform probes by pod IP, so Host is an ephemeral IP:port that can
    never be in ALLOWED_HOSTS. CommonMiddleware.process_request calls
    request.get_host() unconditionally, which raises DisallowedHost (-> 400)
    before the health view would ever run. This middleware must therefore
    run first — before SecurityMiddleware, CommonMiddleware, or anything
    else — and must never call get_host(), build_absolute_uri(), or any
    other ALLOWED_HOSTS-validated accessor. Reading PATH_INFO directly off
    request.META is the only host-independent way to see the path.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.META.get("PATH_INFO") == settings.HEALTH_CHECK_PATH:
            return JsonResponse({"status": "ok"})
        return self.get_response(request)


class NoindexMiddleware:
    """Add X-Robots-Tag to every response while SITE_NOINDEX is on.

    Deliberately independent of SITE_PRIVATE/SitePrivateMiddleware: this
    site can go noindex (still finishing content) while access control is
    handled a different way (e.g. Wagtail-native page privacy), or vice
    versa, so the two must be settable independently.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(settings, "SITE_NOINDEX", False):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response


class SitePrivateMiddleware:
    """Gate the whole site behind HTTP Basic Auth when SITE_PRIVATE is on.

    Fails closed: any missing/malformed credential, header, or config is
    treated as unauthorized rather than allowed through.
    """

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

        return self._handle(request)

    def _handle(self, request):
        if request.path == settings.HEALTH_CHECK_PATH:
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
