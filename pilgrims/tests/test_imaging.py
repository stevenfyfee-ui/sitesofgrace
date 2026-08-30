from django.test import SimpleTestCase
from PIL import Image

from pilgrims import imaging

from .factories import (
    GPS_IFD_TAG,
    ORIENTATION_TAG,
    make_jpeg_bytes,
    make_uploaded_fake_image,
    make_uploaded_jpeg,
)


def _decode(data):
    from io import BytesIO
    img = Image.open(BytesIO(data))
    img.load()
    return img


class ProcessUploadTests(SimpleTestCase):
    def test_rejects_non_image_disguised_as_jpeg(self):
        with self.assertRaises(imaging.UnsupportedImageError):
            imaging.process_upload(make_uploaded_fake_image())

    def test_rejects_oversized_file_before_reading(self):
        upload = make_uploaded_jpeg()
        upload.size = imaging.MAX_UPLOAD_BYTES + 1  # simulate a huge declared size
        with self.assertRaises(imaging.UploadTooLargeError):
            imaging.process_upload(upload)

    def test_accepts_plain_jpeg_and_produces_all_derivatives(self):
        upload = make_uploaded_jpeg(width=2000, height=1000)
        processed = imaging.process_upload(upload)

        self.assertEqual(processed.width, 2000)
        self.assertEqual(processed.height, 1000)
        self.assertEqual(len(processed.content_hash), 64)  # sha256 hex

        original = _decode(processed.original_bytes)
        self.assertEqual(original.format, "JPEG")
        self.assertEqual(original.size, (2000, 1000))  # never downscaled

        large = _decode(processed.large_bytes)
        self.assertEqual(large.format, "JPEG")
        self.assertEqual(max(large.size), imaging.LARGE_MAX_EDGE)

        feed = _decode(processed.feed_bytes)
        self.assertEqual(max(feed.size), imaging.FEED_MAX_EDGE)

        thumb = _decode(processed.thumb_bytes)
        self.assertEqual(thumb.size, (imaging.THUMB_SIZE, imaging.THUMB_SIZE))

    def test_does_not_upscale_small_images(self):
        upload = make_uploaded_jpeg(width=200, height=150)
        processed = imaging.process_upload(upload)
        large = _decode(processed.large_bytes)
        self.assertEqual(large.size, (200, 150))

    def test_strips_gps_but_keeps_orientation_baked_in(self):
        upload = make_uploaded_jpeg(with_gps=True, orientation=6)
        processed = imaging.process_upload(upload)

        original = _decode(processed.original_bytes)
        exif = original.getexif()
        self.assertNotIn(GPS_IFD_TAG, exif, "GPS EXIF tag must be stripped from the stored original")
        # exif_transpose applies the rotation to pixels and resets
        # Orientation to the identity value (or removes it) — either way,
        # no consumer downstream needs to re-rotate this image.
        self.assertIn(exif.get(ORIENTATION_TAG, 1), (1,))

    def test_derivatives_also_have_no_gps(self):
        upload = make_uploaded_jpeg(with_gps=True)
        processed = imaging.process_upload(upload)
        for data in (processed.large_bytes, processed.feed_bytes, processed.thumb_bytes):
            exif = _decode(data).getexif()
            self.assertNotIn(GPS_IFD_TAG, exif)

    def test_rejects_svg(self):
        svg = make_uploaded_fake_image()
        svg.name = "picture.svg"
        # Content is not an image regardless of the .svg name/content-type —
        # confirms rejection is format-decode-based, not extension-based.
        with self.assertRaises(imaging.UnsupportedImageError):
            imaging.process_upload(svg)

    def test_content_hash_is_stable_for_identical_uploads(self):
        data = make_jpeg_bytes()
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload_a = SimpleUploadedFile("a.jpg", data, content_type="image/jpeg")
        upload_b = SimpleUploadedFile("b.jpg", data, content_type="image/jpeg")
        processed_a = imaging.process_upload(upload_a)
        processed_b = imaging.process_upload(upload_b)
        self.assertEqual(processed_a.content_hash, processed_b.content_hash)
