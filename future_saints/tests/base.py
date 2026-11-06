import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from wagtail.models import Site

from future_saints.models import FutureSaintsHomePage, FutureSaintsIndexPage

FS_OFF = override_settings(SOG_FUTURE_SAINTS="off")
FS_STAFF = override_settings(SOG_FUTURE_SAINTS="staff")
FS_ON = override_settings(SOG_FUTURE_SAINTS="on")


class FutureSaintsTestCase(TestCase):
    """The Future Saints tree, built by the real command and published."""

    def setUp(self):
        # Other apps' tests create extra Sites; Wagtail caches site root paths
        # process-wide, and a stale cache turns page.url into None here.
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        media_override = override_settings(MEDIA_ROOT=media)
        media_override.enable()
        self.addCleanup(media_override.disable)

        call_command("create_future_saints_tree", stdout=StringIO())
        self.home = FutureSaintsHomePage.objects.get()
        self.publish(self.home)
        for index in FutureSaintsIndexPage.objects.child_of(self.home):
            self.publish(index)
        self.home.refresh_from_db()
        self.saints = FutureSaintsIndexPage.objects.get(content_kind="saint")

        User = get_user_model()
        self.staff = User.objects.create_user("fs-staff", "staff@example.com", "x", is_staff=True)
        self.visitor = User.objects.create_user("fs-visitor", "visitor@example.com", "x")

    @staticmethod
    def publish(page):
        page.specific.save_revision().publish()

    def get(self, url, user=None, **params):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        return self.client.get(url, params)

    def html(self, url, user=None, **params):
        response = self.get(url, user, **params)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()
