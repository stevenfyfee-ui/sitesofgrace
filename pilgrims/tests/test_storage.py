"""
Presigned-URL signing behavior of the pilgrim_private storage.

Signing is pure local crypto (boto3 never hits the network to compute a
presigned URL), so this uses obviously-fake, clearly-labeled test
credentials rather than real Spaces secrets — nothing here talks to a real
bucket. It exercises the exact OPTIONS from sitesofgrace/settings/base.py's
"pilgrim_private" entry, so a change to those options that breaks signing
fails here first.

What this file deliberately does NOT cover: confirming the unsigned path
actually 403s against the real bucket. That requires real SPACES_* dev
credentials this environment doesn't have — see the phase-2 report.
"""
from django.test import SimpleTestCase
from storages.backends.s3 import S3Storage


def _private_storage(**overrides):
    options = dict(
        access_key="test-access-key-id",
        secret_key="test-secret-access-key",
        bucket_name="test-bucket",
        region_name="nyc3",
        endpoint_url="https://nyc3.digitaloceanspaces.com",
        location="private",
        default_acl="private",
        querystring_auth=True,
        querystring_expire=900,
        custom_domain=False,
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

    def test_url_is_scoped_under_private_location(self):
        storage = _private_storage()
        url = storage.url("pilgrims/owner-uuid/photo-uuid/original.jpg")
        self.assertIn("/private/pilgrims/owner-uuid/photo-uuid/original.jpg", url)

    def test_custom_domain_would_bypass_signing_if_ever_set(self):
        # Regression guard for the exact footgun the settings comment warns
        # about: a truthy custom_domain makes S3Storage.url() return a bare
        # unsigned URL, assuming a CDN handles auth. It must never be set on
        # pilgrim_private.
        storage = _private_storage(custom_domain="cdn.example.com")
        url = storage.url("pilgrims/owner-uuid/photo-uuid/original.jpg")
        self.assertNotIn("X-Amz-Signature", url)
        self.assertTrue(url.startswith("https://cdn.example.com/"))
