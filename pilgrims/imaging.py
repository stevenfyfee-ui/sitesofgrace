"""
Upload validation, EXIF/GPS handling, and derivative generation for pilgrim
photos. Pure and storage-agnostic: everything here works on bytes in memory
and returns a ProcessedPhoto: callers (pilgrims/views.py) decide what to
persist and where.

Format is decided by what Pillow can actually decode, never by filename or
Content-Type — a renamed .txt never gets past process_upload().
"""
import hashlib
import io

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only if the dep is missing
    HEIF_AVAILABLE = False

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
if HEIF_AVAILABLE:
    ACCEPTED_FORMATS.add("HEIF")

LARGE_MAX_EDGE = 1600
FEED_MAX_EDGE = 1200
THUMB_SIZE = 400
DERIVATIVE_QUALITY = 85
ORIGINAL_JPEG_QUALITY = 95

GPS_IFD_TAG = 0x8825  # "GPSInfo" — the whole GPS sub-IFD, removed wholesale.


class UnsupportedImageError(Exception):
    """Not a decodable image, or a format we don't accept."""


class UploadTooLargeError(Exception):
    """Raised from the file's declared size, before any read()."""


class ProcessedPhoto:
    def __init__(self, *, original_bytes, original_ext, large_bytes, feed_bytes,
                 thumb_bytes, width, height, byte_size, content_hash):
        self.original_bytes = original_bytes
        self.original_ext = original_ext
        self.large_bytes = large_bytes
        self.feed_bytes = feed_bytes
        self.thumb_bytes = thumb_bytes
        self.width = width
        self.height = height
        self.byte_size = byte_size
        self.content_hash = content_hash


def _strip_gps(image):
    exif = image.getexif()
    if GPS_IFD_TAG in exif:
        del exif[GPS_IFD_TAG]
    return exif


def _resize_within(image, max_edge):
    width, height = image.size
    if max(width, height) <= max_edge:
        return image.copy()
    ratio = max_edge / float(max(width, height))
    new_size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
    return image.resize(new_size, Image.LANCZOS)


def _encode_jpeg(image, quality):
    buf = io.BytesIO()
    rgb = image.convert("RGB") if image.mode not in ("RGB", "L") else image
    rgb.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def process_upload(uploaded_file):
    """uploaded_file: a Django UploadedFile. Raises UploadTooLargeError or
    UnsupportedImageError; otherwise returns a ProcessedPhoto."""
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError(
            f"That file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    raw_bytes = uploaded_file.read()

    try:
        probe = Image.open(io.BytesIO(raw_bytes))
        probe.verify()
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except Exception as exc:
        raise UnsupportedImageError("That file isn't a readable image.") from exc

    detected_format = (image.format or "").upper()
    if detected_format not in ACCEPTED_FORMATS:
        raise UnsupportedImageError(f"Unsupported image format: {detected_format or 'unknown'}.")

    # Orientation baked into pixels first (also normalizes the Orientation
    # tag), then GPS stripped from what actually gets stored — including the
    # "untouched" original.
    image = ImageOps.exif_transpose(image)
    exif = _strip_gps(image)
    width, height = image.size

    if detected_format == "HEIF":
        # HEIC always becomes JPEG — nothing downstream (browsers, the
        # postcard/print product this original exists for) can rely on HEIC.
        original_bytes = _encode_jpeg(image, ORIGINAL_JPEG_QUALITY)
        original_ext = "jpg"
    elif detected_format == "PNG":
        buf = io.BytesIO()
        image.save(buf, format="PNG", exif=exif)
        original_bytes = buf.getvalue()
        original_ext = "png"
    elif detected_format == "WEBP":
        buf = io.BytesIO()
        image.save(buf, format="WEBP", quality=ORIGINAL_JPEG_QUALITY, exif=exif)
        original_bytes = buf.getvalue()
        original_ext = "webp"
    else:  # JPEG
        buf = io.BytesIO()
        image.convert("RGB").save(
            buf, format="JPEG", quality=ORIGINAL_JPEG_QUALITY,
            optimize=True, progressive=True, exif=exif,
        )
        original_bytes = buf.getvalue()
        original_ext = "jpg"

    # Derivatives are always re-encoded JPEG, regardless of source format.
    large_bytes = _encode_jpeg(_resize_within(image, LARGE_MAX_EDGE), DERIVATIVE_QUALITY)
    feed_bytes = _encode_jpeg(_resize_within(image, FEED_MAX_EDGE), DERIVATIVE_QUALITY)
    thumb_source = ImageOps.fit(image.convert("RGB"), (THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
    thumb_bytes = _encode_jpeg(thumb_source, DERIVATIVE_QUALITY)

    # Hash of the original AS STORED (GPS-stripped, oriented) — not the raw
    # upload — since that's what duplicate detection is actually protecting.
    content_hash = hashlib.sha256(original_bytes).hexdigest()

    return ProcessedPhoto(
        original_bytes=original_bytes,
        original_ext=original_ext,
        large_bytes=large_bytes,
        feed_bytes=feed_bytes,
        thumb_bytes=thumb_bytes,
        width=width,
        height=height,
        byte_size=len(original_bytes),
        content_hash=content_hash,
    )
