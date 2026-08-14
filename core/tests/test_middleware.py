import base64

from django.conf import settings
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings

from core.middleware import HealthCheckMiddleware, NoindexMiddleware, SitePrivateMiddleware
from core.views import robots_txt


def _get_response(request):
    return HttpResponse("ok", status=200)


def _basic_auth_header(username, password):
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


class SitePrivateMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SitePrivateMiddleware(_get_response)

    def _request(self, path="/", auth_header=None):
        kwargs = {}
        if auth_header is not None:
            kwargs["HTTP_AUTHORIZATION"] = auth_header
        return self.factory.get(path, **kwargs)

    @override_settings(SITE_PRIVATE=False)
    def test_inactive_is_noop(self):
        request = self._request()
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WWW-Authenticate", response)
        self.assertNotIn("X-Robots-Tag", response)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_active_no_header_401(self):
        response = self.middleware(self._request())
        self.assertEqual(response.status_code, 401)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_active_correct_credentials_passes_through(self):
        auth = _basic_auth_header("editor", "secret")
        response = self.middleware(self._request(auth_header=auth))
        self.assertEqual(response.status_code, 200)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_wrong_password_401(self):
        auth = _basic_auth_header("editor", "wrong")
        response = self.middleware(self._request(auth_header=auth))
        self.assertEqual(response.status_code, 401)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_wrong_username_401(self):
        auth = _basic_auth_header("intruder", "secret")
        response = self.middleware(self._request(auth_header=auth))
        self.assertEqual(response.status_code, 401)

    @override_settings(
        SITE_PRIVATE=True,
        SITE_PRIVATE_USER="editor",
        SITE_PRIVATE_PASSWORD="pass:with:colons",
    )
    def test_password_containing_colon_passes_through(self):
        auth = _basic_auth_header("editor", "pass:with:colons")
        response = self.middleware(self._request(auth_header=auth))
        self.assertEqual(response.status_code, 200)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_malformed_headers_401_without_raising(self):
        valid_b64_no_colon = base64.b64encode(b"nocolonhere").decode("ascii")
        cases = {
            "header absent": None,
            "no space in header": "Basic",
            "scheme not basic": "Bearer " + base64.b64encode(b"editor:secret").decode("ascii"),
            "base64 does not decode": "Basic ***not-base64***",
            "invalid utf-8 bytes": "Basic " + base64.b64encode(b"\xff\xfe\xfd").decode("ascii"),
            "no colon in decoded value": f"Basic {valid_b64_no_colon}",
        }
        for label, header in cases.items():
            with self.subTest(label):
                response = self.middleware(self._request(auth_header=header))
                self.assertEqual(response.status_code, 401)

    @override_settings(SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="")
    def test_empty_password_setting_fails_closed(self):
        auth = _basic_auth_header("editor", "")
        response = self.middleware(self._request(auth_header=auth))
        self.assertEqual(response.status_code, 401)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_health_check_path_bypasses_auth(self):
        response = self.middleware(self._request(path=settings.HEALTH_CHECK_PATH))
        self.assertEqual(response.status_code, 200)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_static_url_is_gated(self):
        response = self.middleware(self._request(path="/static/site.css"))
        self.assertEqual(response.status_code, 401)

    @override_settings(
        SITE_PRIVATE=True, SITE_PRIVATE_USER="editor", SITE_PRIVATE_PASSWORD="secret"
    )
    def test_does_not_set_x_robots_tag_itself(self):
        # X-Robots-Tag is now driven solely by SITE_NOINDEX via
        # NoindexMiddleware (see NoindexMiddlewareTests below) — access
        # control and crawler exposure are independent settings.
        response = self.middleware(self._request())
        self.assertNotIn("X-Robots-Tag", response)

        auth = _basic_auth_header("editor", "secret")
        response = self.middleware(self._request(auth_header=auth))
        self.assertNotIn("X-Robots-Tag", response)

    def test_www_authenticate_survives_header_encoding_unmangled(self):
        # Guards against a real regression: a non-ASCII realm gets MIME-encoded
        # by Django's header machinery, destroying the leading "Basic " token
        # and leaving browsers unable to parse this as an auth challenge.
        middleware = SitePrivateMiddleware(_get_response)
        response = middleware._unauthorized()

        self.assertEqual(
            response["WWW-Authenticate"], SitePrivateMiddleware.WWW_AUTHENTICATE
        )
        self.assertTrue(response["WWW-Authenticate"].startswith("Basic "))
        # Must not raise: this is what Django's header serialization does
        # internally, and a non-latin-1 value would be silently MIME-encoded
        # instead of failing loudly here.
        SitePrivateMiddleware.WWW_AUTHENTICATE.encode("latin-1")


class HealthCheckMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_health_path_returns_200_without_calling_get_response(self):
        def _explodes(request):
            raise AssertionError("get_response must not be called for the health path")

        middleware = HealthCheckMiddleware(_explodes)
        request = self.factory.get(settings.HEALTH_CHECK_PATH)
        response = middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})

    def test_non_health_path_passes_through(self):
        middleware = HealthCheckMiddleware(_get_response)
        response = middleware(self.factory.get("/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_health_bypasses_allowed_hosts(self):
        # Regression test for the production outage: App Platform's
        # readiness probe hits /health/ using the pod's ephemeral IP as
        # Host, which can never be in ALLOWED_HOSTS. Before
        # HealthCheckMiddleware existed, CommonMiddleware.process_request
        # called request.get_host() unconditionally and raised
        # DisallowedHost (-> 400) before the health view ever ran. This
        # exercises the real middleware chain (not just this middleware in
        # isolation), so it would have failed against the old code.
        middleware_stack = [
            "core.middleware.HealthCheckMiddleware",
            "django.middleware.common.CommonMiddleware",
        ]
        with override_settings(ALLOWED_HOSTS=["example.com"], MIDDLEWARE=middleware_stack):
            client = Client()
            response = client.get(settings.HEALTH_CHECK_PATH, HTTP_HOST="10.1.2.3:8080")
        self.assertEqual(response.status_code, 200)

    def test_health_bypasses_site_private_gate(self):
        middleware_stack = [
            "core.middleware.HealthCheckMiddleware",
            "core.middleware.SitePrivateMiddleware",
        ]
        with override_settings(
            SITE_PRIVATE=True,
            SITE_PRIVATE_USER="editor",
            SITE_PRIVATE_PASSWORD="secret",
            MIDDLEWARE=middleware_stack,
        ):
            client = Client()
            response = client.get(settings.HEALTH_CHECK_PATH)
        self.assertEqual(response.status_code, 200)

    def test_non_health_path_disallowed_host_still_400(self):
        # Proves HealthCheckMiddleware only exempts the health path — it
        # doesn't accidentally swallow ALLOWED_HOSTS validation for
        # everything else.
        middleware_stack = [
            "core.middleware.HealthCheckMiddleware",
            "django.middleware.common.CommonMiddleware",
        ]
        with override_settings(ALLOWED_HOSTS=["example.com"], MIDDLEWARE=middleware_stack):
            client = Client()
            response = client.get("/", HTTP_HOST="10.1.2.3:8080")
        self.assertEqual(response.status_code, 400)


class NoindexMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = NoindexMiddleware(_get_response)

    @override_settings(SITE_NOINDEX=True)
    def test_header_present_when_active(self):
        response = self.middleware(self.factory.get("/"))
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    @override_settings(SITE_NOINDEX=False)
    def test_header_absent_when_inactive(self):
        response = self.middleware(self.factory.get("/"))
        self.assertNotIn("X-Robots-Tag", response)

    @override_settings(SITE_NOINDEX=True)
    def test_applies_regardless_of_site_private(self):
        # Must apply to every response, not only ones that happen to pass
        # through SitePrivateMiddleware's gate.
        def _unauthorized(request):
            return HttpResponse("Authentication required", status=401)

        middleware = NoindexMiddleware(_unauthorized)
        response = middleware(self.factory.get("/"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")


class RobotsTxtViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(SITE_NOINDEX=True)
    def test_noindex_true_disallows_all(self):
        response = robots_txt(self.factory.get("/robots.txt"))
        self.assertIn(b"Disallow: /", response.content)

    @override_settings(SITE_NOINDEX=False)
    def test_noindex_false_allows_and_points_at_sitemap(self):
        response = robots_txt(self.factory.get("/robots.txt"))
        self.assertIn(b"Allow: /", response.content)
        self.assertIn(b"Sitemap:", response.content)
        self.assertNotIn(b"Disallow:", response.content)
