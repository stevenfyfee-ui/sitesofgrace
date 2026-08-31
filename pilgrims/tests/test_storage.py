"""
Presigned-URL signing behavior of the pilgrim_private storage.

Signing is pure local crypto (boto3 never hits the network to compute a
presigned URL), so this uses obviously-fake, clearly-labeled test
credentials rather than real Spaces secrets — nothing here talks to a real
bucket. It exercises the exact OPTIONS from sitesofgrace/settings/base.py's
"pilgrim_private" entry (a separate bucket/key from "default", no
"location" prefix — the whole bucket is private), so a change to those
options that breaks signing fails here first.

Everything in this file was subsequently confirmed against the real
sitesofgrace-pilgrims bucket by a one-off script (not part of the suite,
since it needs real SPACES_PRIVATE_* credentials this environment doesn't
reliably have) — see the phase-2 live-verification report: multipart
upload past the 8MB threshold, presigned URL host/signature, unsigned-path
403, HeadObject existence checks (object-level only, never a bucket-level
List call — the Limited Access key can't do those), 10s-expiry 403, and
delete removing all four derivatives.
"""
from urllib.parse import urlparse

from django.conf import settings
from django.test import SimpleTestCase
from storages.backends.s3 import S3Storage


def _private_storage(**overrides):
    options = dict(
        access_key="test-private-access-key-id",
        secret_key="test-private-secret-access-key",
        bucket_name="sitesofgrace-pilgrims",
        region_name="sfo3",
        endpoint_url="https://sfo3.digitaloceanspaces.com",
        default_acl="private",
        querystring_auth=True,
        querystring_expire=900,
        custom_domain=None,
        file_overwrite=False,
    )
    options.update(overrides)
    return S3Storage(**options)


class PrivateStorageSigningTests(SimpleTestCase):
    def test_url_is_presigned(self):
        storage = _private_storage()
        url = storage.url("pilgrims/owner-uuid/photo-uuid/original.jpg")
        self.assertIn("X-Amz-Signature=", url)
        self.assertIn("X-Amz-Expires=900", url)

    def test_url_has_no_private_location_prefix(self):
        # The pilgrim_private bucket is entirely private — unlike an early
        # draft of this config, there is no "location" prefix to add.
        storage = _private_storage()
        url = storage.url("pilgrims/owner-uuid/photo-uuid/original.jpg")
        self.assertIn("/pilgrims/owner-uuid/photo-uuid/original.jpg", url)
        self.assertNotIn("/private/pilgrims/", url)

    def test_url_host_is_the_plain_sfo3_endpoint_not_a_cdn_domain(self):
        storage = _private_storage()
        url = storage.url("pilgrims/owner-uuid/photo-uuid/original.jpg")
        host = urlparse(url).netloc
        self.assertTrue(
            host.endswith("sfo3.digitaloceanspaces.com"),
            f"expected the plain sfo3 endpoint, got {host!r}",
        )

    def test_custom_domain_would_bypass_signing_if_ever_set(self):
        # Regression guard for the exact footgun the settings comment warns
        # about: a truthy custom_domain makes S3Storage.url() return a bare
        # unsigned URL, assuming a CDN handles auth. It must never be set on
        # pilgrim_private — that bucket has no CDN anyway.
        storage = _private_storage(custom_domain="cdn.example.com")
        url = storage.url("pilgrims/owner-uuid/photo-uuid/original.jpg")
        self.assertNotIn("X-Amz-Signature", url)
        self.assertTrue(url.startswith("https://cdn.example.com/"))


class MultipartUploadThresholdTests(SimpleTestCase):
    """A real phone photo is typically well over 8MB. boto3's S3 transfer
    manager switches from a single PutObject to
    CreateMultipartUpload/UploadPart/CompleteMultipartUpload above its
    `multipart_threshold` — a different call set, against the same scoped
    Limited Access key. Confirmed live (see module docstring) that an
    8.06MB upload through the real view succeeds; these guard against a
    future config change silently disabling that path without anyone
    re-running the live check."""

    def test_pilgrim_private_options_do_not_override_transfer_config(self):
        # The only way to change the multipart threshold/behavior is a
        # "transfer_config" (or legacy AWS_S3_TRANSFER_CONFIG) OPTIONS key.
        # base.py must never add one without a deliberate reason.
        options = settings.STORAGES["pilgrim_private"]["OPTIONS"]
        self.assertNotIn("transfer_config", options)

    def test_default_transfer_config_multipart_threshold_is_8mb(self):
        storage = _private_storage()
        self.assertEqual(storage.transfer_config.multipart_threshold, 8 * 1024 * 1024)

    def test_default_transfer_config_multipart_chunksize_is_8mb(self):
        storage = _private_storage()
        self.assertEqual(storage.transfer_config.multipart_chunksize, 8 * 1024 * 1024)


class RealSettingsConfigTests(SimpleTestCase):
    """Guards the actual sitesofgrace/settings/base.py OPTIONS dict itself
    (not just the reconstructed fixture above) against silent drift on any
    of the values the live verification depends on."""

    def test_pilgrim_private_options(self):
        options = settings.STORAGES["pilgrim_private"]["OPTIONS"]
        self.assertEqual(options["region_name"], "sfo3")
        self.assertEqual(options["endpoint_url"], "https://sfo3.digitaloceanspaces.com")
        self.assertIsNone(options["custom_domain"])
        self.assertTrue(options["querystring_auth"])
        self.assertEqual(options["querystring_expire"], 900)
        self.assertEqual(options["default_acl"], "private")
        # Required so Storage.save() never calls HeadObject to check for a
        # collision before saving — every key here is UUID-based and can't
        # really collide, and this key can't distinguish "doesn't exist"
        # from "forbidden" without s3:ListBucket (confirmed live: HeadObject
        # on a key that never existed returns 403, not 404).
        self.assertTrue(options["file_overwrite"])
        self.assertNotIn("location", options)
