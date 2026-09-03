from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from .. import sharing
from ..models import ModerationAction, PhotoReport, PilgrimPhoto
from ..permissions import staff_can_view_reported_photo
from ..views import _client_ip, _ip_hash
from .factories import grant_wagtail_admin_access
from .test_sharing import _make_photo, _make_site, _PublicAndPrivateStorageTestCase


class ClientIpSpoofingTests(_PublicAndPrivateStorageTestCase):
    """The security bug: split(",")[0] on X-Forwarded-For trusts whatever
    the CLIENT put there. App Platform's edge proxy appends the real
    address rather than replacing the header, so a forged
    "X-Forwarded-For: 1.2.3.4" becomes "1.2.3.4, <real ip>" by the time it
    reaches Django — the real ip is on the RIGHT, and with exactly one
    trusted hop (the default) that's the only entry that should count."""

    def setUp(self):
        self.factory = RequestFactory()

    def _request_with_xff(self, xff, remote_addr="203.0.113.9"):
        request = self.factory.get("/pilgrims/photos/x/report/")
        request.META["HTTP_X_FORWARDED_FOR"] = xff
        request.META["REMOTE_ADDR"] = remote_addr
        return request

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_forged_leftmost_entry_is_ignored(self):
        # Attacker sends X-Forwarded-For: 9.9.9.9 ; the one trusted proxy in
        # front of the app appends the real address behind it.
        request = self._request_with_xff("9.9.9.9, 198.51.100.7")
        self.assertEqual(_client_ip(request), "198.51.100.7")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_rotating_the_forged_prefix_does_not_change_the_hash(self):
        # The whole point of the attack: spoof a different leftmost value
        # per request to look like a different reporter/uploader each time.
        # If the fix works, every one of these hashes to the same value,
        # because only the trusted (rightmost) hop is ever read.
        real_hop = "198.51.100.7"
        hashes = {
            _ip_hash(self._request_with_xff(f"{fake}, {real_hop}"))
            for fake in ("1.1.1.1", "2.2.2.2", "9.9.9.9", "not-even-an-ip")
        }
        self.assertEqual(len(hashes), 1, "rotating the spoofed prefix must not change the computed hash")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_no_xff_header_falls_back_to_remote_addr(self):
        request = self.factory.get("/pilgrims/photos/x/report/")
        request.META["REMOTE_ADDR"] = "203.0.113.9"
        self.assertEqual(_client_ip(request), "203.0.113.9")

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_fewer_hops_than_trusted_falls_back_to_remote_addr(self):
        # With 2 trusted hops configured, a header with only 1 entry isn't
        # enough to confidently identify which position is trustworthy —
        # don't guess, fall back to the safe default rather than trusting
        # the one (possibly attacker-supplied) entry present.
        request = self._request_with_xff("9.9.9.9")
        self.assertEqual(_client_ip(request), "203.0.113.9")

    def test_report_rate_limit_cannot_be_bypassed_by_rotating_xff(self):
        owner = User.objects.create_user("xff_owner", "xff_owner@example.com", "pw")
        site = _make_site(slug="xff-site")
        photos = [_make_photo(owner, site, width=50 + i, height=50 + i) for i in range(10)]
        for p in photos:
            sharing.share_photo(p, credit="display_name")

        client = Client()
        real_hop = "198.51.100.55"
        for i, photo in enumerate(photos):
            client.post(
                reverse("pilgrims:report_photo", args=[photo.uuid]),
                {"reason": PhotoReport.REASON_COPYRIGHT},
                # A different forged leftmost value every request, same
                # trusted rightmost hop each time.
                HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, {real_hop}",
                REMOTE_ADDR="192.0.2.100",  # the proxy's own address, not the client's
            )

        one_more = _make_photo(owner, site, width=999, height=999)
        sharing.share_photo(one_more, credit="display_name")
        response = client.post(
            reverse("pilgrims:report_photo", args=[one_more.uuid]),
            {"reason": PhotoReport.REASON_COPYRIGHT},
            HTTP_X_FORWARDED_FOR=f"10.0.0.99, {real_hop}",
            REMOTE_ADDR="192.0.2.100",
        )
        data = response.json()
        self.assertFalse(data["success"], "rotating the spoofed XFF prefix must not bypass the rate limit")
        self.assertEqual(data["error"], "rate_limited")


class AutoHideTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("hide_owner", "hide_owner@example.com", "pw")
        self.site = _make_site(slug="hide-site")
        self.photo = _make_photo(self.owner, self.site)
        sharing.share_photo(self.photo, credit="display_name")
        self.client = Client()

    def _report(self, reason, reporter_ip_hash="hash-a", note=""):
        return self.client.post(reverse("pilgrims:report_photo", args=[self.photo.uuid]), {
            "reason": reason, "note": note,
        })

    def test_sexual_report_hides_on_first_report_and_removes_public_objects(self):
        storage = self.photo.public_large.storage
        large_path = self.photo.public_large.name

        response = self._report(PhotoReport.REASON_SEXUAL)
        self.assertTrue(response.json()["success"])

        self.photo.refresh_from_db()
        self.assertTrue(self.photo.hidden_by_staff)
        self.assertFalse(storage.exists(large_path))
        self.assertFalse(bool(self.photo.public_large))

    def test_minor_safety_and_violence_also_hide_immediately(self):
        for reason in (PhotoReport.REASON_MINOR_SAFETY, PhotoReport.REASON_VIOLENCE):
            photo = _make_photo(self.owner, self.site, width=100, height=100)
            sharing.share_photo(photo, credit="display_name")
            self.client.post(reverse("pilgrims:report_photo", args=[photo.uuid]), {"reason": reason})
            photo.refresh_from_db()
            self.assertTrue(photo.hidden_by_staff, f"{reason} should auto-hide on first report")

    def test_other_reason_does_not_hide_on_first_report(self):
        response = self._report(PhotoReport.REASON_COPYRIGHT)
        self.assertTrue(response.json()["success"])
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.hidden_by_staff)
        self.assertTrue(bool(self.photo.public_large))

    def test_other_reason_hides_at_two_distinct_reporters(self):
        client_a = Client()
        client_b = Client()
        # Different REMOTE_ADDR -> different ip_hash for each anonymous client.
        client_a.post(
            reverse("pilgrims:report_photo", args=[self.photo.uuid]),
            {"reason": PhotoReport.REASON_COPYRIGHT},
            REMOTE_ADDR="10.0.0.1",
        )
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.hidden_by_staff, "one reporter must not be enough")

        client_b.post(
            reverse("pilgrims:report_photo", args=[self.photo.uuid]),
            {"reason": PhotoReport.REASON_OTHER},
            REMOTE_ADDR="10.0.0.2",
        )
        self.photo.refresh_from_db()
        self.assertTrue(self.photo.hidden_by_staff, "two distinct reporters should hide it")

    def test_same_reporter_reporting_twice_does_not_count_as_two(self):
        for _ in range(3):
            self.client.post(
                reverse("pilgrims:report_photo", args=[self.photo.uuid]),
                {"reason": PhotoReport.REASON_COPYRIGHT},
                REMOTE_ADDR="10.0.0.9",
            )
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.hidden_by_staff, "repeated reports from one IP are one reporter")

    def test_hidden_photo_stays_hidden_idempotently(self):
        self._report(PhotoReport.REASON_SEXUAL)
        self.photo.refresh_from_db()
        first_hidden_at = self.photo.hidden_at
        self._report(PhotoReport.REASON_VIOLENCE)
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.hidden_at, first_hidden_at)


class ReportEmailAndRateLimitTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("email_owner", "email_owner@example.com", "pw")
        self.site = _make_site(slug="email-site")
        self.photo = _make_photo(self.owner, self.site)
        sharing.share_photo(self.photo, credit="display_name")
        self.client = Client()

    def test_report_sends_moderation_email(self):
        mail.outbox = []
        self.client.post(
            reverse("pilgrims:report_photo", args=[self.photo.uuid]),
            {"reason": PhotoReport.REASON_COPYRIGHT}, REMOTE_ADDR="10.1.1.1",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reported", mail.outbox[0].subject.lower())

    def test_report_rate_limit_per_ip(self):
        from ..views import REPORTS_PER_HOUR_PER_IP

        photos = [_make_photo(self.owner, self.site, width=50 + i, height=50 + i) for i in range(REPORTS_PER_HOUR_PER_IP)]
        for photo in photos:
            sharing.share_photo(photo, credit="display_name")
            self.client.post(
                reverse("pilgrims:report_photo", args=[photo.uuid]),
                {"reason": PhotoReport.REASON_COPYRIGHT}, REMOTE_ADDR="10.2.2.2",
            )

        one_more = _make_photo(self.owner, self.site, width=999, height=999)
        sharing.share_photo(one_more, credit="display_name")
        response = self.client.post(
            reverse("pilgrims:report_photo", args=[one_more.uuid]),
            {"reason": PhotoReport.REASON_COPYRIGHT}, REMOTE_ADDR="10.2.2.2",
        )
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "rate_limited")

    def test_report_rate_limit_scoped_per_ip(self):
        from ..views import REPORTS_PER_HOUR_PER_IP

        photos = [_make_photo(self.owner, self.site, width=50 + i, height=50 + i) for i in range(REPORTS_PER_HOUR_PER_IP)]
        for photo in photos:
            sharing.share_photo(photo, credit="display_name")
            self.client.post(
                reverse("pilgrims:report_photo", args=[photo.uuid]),
                {"reason": PhotoReport.REASON_COPYRIGHT}, REMOTE_ADDR="10.3.3.3",
            )

        # A different IP should be unaffected by the first IP's cap.
        one_more = _make_photo(self.owner, self.site, width=999, height=999)
        sharing.share_photo(one_more, credit="display_name")
        response = self.client.post(
            reverse("pilgrims:report_photo", args=[one_more.uuid]),
            {"reason": PhotoReport.REASON_COPYRIGHT}, REMOTE_ADDR="10.3.3.4",
        )
        self.assertTrue(response.json()["success"])


class StaffModerationPermissionTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("mod_owner", "mod_owner@example.com", "pw")
        self.staff = User.objects.create_user("mod_staff", "mod_staff@example.com", "pw", is_staff=True)
        grant_wagtail_admin_access(self.staff)
        self.site = _make_site(slug="mod-site")
        self.reported_photo = _make_photo(self.owner, self.site, width=101, height=101)
        self.unreported_photo = _make_photo(self.owner, self.site, width=102, height=102)
        sharing.share_photo(self.reported_photo, credit="display_name")
        sharing.share_photo(self.unreported_photo, credit="display_name")
        PhotoReport.objects.create(
            photo=self.reported_photo, reporter_ip_hash="x", reason=PhotoReport.REASON_COPYRIGHT,
        )

    def test_staff_can_view_reported_photo_and_it_is_logged(self):
        self.assertEqual(ModerationAction.objects.count(), 0)
        result = staff_can_view_reported_photo(self.staff, self.reported_photo)
        self.assertTrue(result)
        self.assertEqual(ModerationAction.objects.count(), 1)
        action = ModerationAction.objects.first()
        self.assertEqual(action.actor, self.staff)
        self.assertEqual(action.action, ModerationAction.ACTION_VIEW_REPORTED_PHOTO)
        self.assertEqual(action.photo, self.reported_photo)

    def test_staff_cannot_view_unreported_photo(self):
        result = staff_can_view_reported_photo(self.staff, self.unreported_photo)
        self.assertFalse(result)
        self.assertEqual(ModerationAction.objects.count(), 0)

    def test_non_staff_cannot_view_via_this_function(self):
        follower = User.objects.create_user("mod_follower", "mod_follower@example.com", "pw")
        result = staff_can_view_reported_photo(follower, self.reported_photo)
        self.assertFalse(result)

    def test_moderation_detail_view_403s_for_unreported_photo(self):
        client = Client()
        client.force_login(self.staff)
        response = client.get(
            reverse("pilgrim_moderation_photo_detail", args=[self.unreported_photo.uuid])
        )
        self.assertEqual(response.status_code, 404)

    def test_moderation_detail_view_works_for_reported_photo(self):
        client = Client()
        client.force_login(self.staff)
        response = client.get(
            reverse("pilgrim_moderation_photo_detail", args=[self.reported_photo.uuid])
        )
        self.assertEqual(response.status_code, 200)

    def test_moderation_hide_action_writes_moderation_action_and_hides(self):
        client = Client()
        client.force_login(self.staff)
        response = client.post(
            reverse("pilgrim_moderation_action", args=[self.reported_photo.uuid]),
            {"action": "hide", "reason": "test hide"},
        )
        self.assertEqual(response.status_code, 302)
        self.reported_photo.refresh_from_db()
        self.assertTrue(self.reported_photo.hidden_by_staff)
        self.assertTrue(
            ModerationAction.objects.filter(
                actor=self.staff, action=ModerationAction.ACTION_HIDE, photo=self.reported_photo
            ).exists()
        )

    def test_delete_photo_action_survives_in_moderation_log_after_photo_gone(self):
        client = Client()
        client.force_login(self.staff)
        photo_pk = self.reported_photo.pk
        client.post(
            reverse("pilgrim_moderation_action", args=[self.reported_photo.uuid]),
            {"action": "delete_photo"},
        )
        self.assertFalse(PilgrimPhoto.objects.filter(pk=photo_pk).exists())
        action = ModerationAction.objects.get(action=ModerationAction.ACTION_DELETE_PHOTO)
        self.assertIsNone(action.photo)  # SET_NULL, but the row itself survives
        self.assertEqual(action.owner_affected, self.owner)
