"""Re-encode existing pilgrim avatars with no EXIF metadata.

    python manage.py strip_avatar_exif [--dry-run]

New uploads are cleaned in PilgrimProfile.save(); this catches the ones
uploaded before that. Each avatar goes through the same function public
gallery copies use (imaging.strip_all_exif_jpeg) and is saved under a new
random name, and the old file is deleted -- a CDN-cached copy of the old
URL stops being referenced. Avatars that are already EXIF-free JPEGs are
skipped, so running it twice is harmless.
"""
import io
import uuid

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image

from pilgrims import imaging
from pilgrims.models import PilgrimProfile


def _already_clean(data):
    try:
        image = Image.open(io.BytesIO(data))
        return image.format == "JPEG" and not image.getexif() and "exif" not in image.info
    except Exception:
        return False


class Command(BaseCommand):
    help = "Strip EXIF metadata from every existing pilgrim avatar."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count only; change nothing.")

    def handle(self, *args, **options):
        cleaned = skipped = failed = 0
        for profile in PilgrimProfile.objects.exclude(avatar="").exclude(avatar__isnull=True):
            old = profile.avatar
            try:
                with old.open("rb") as f:
                    data = f.read()
            except Exception as exc:
                failed += 1
                self.stderr.write(f"  profile {profile.pk}: couldn't read the avatar ({type(exc).__name__})")
                continue
            if _already_clean(data):
                skipped += 1
                continue
            if options["dry_run"]:
                cleaned += 1
                continue
            try:
                new_bytes = imaging.strip_all_exif_jpeg(data)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"  profile {profile.pk}: not a readable image ({type(exc).__name__})")
                continue
            old_name = old.name
            storage = old.storage
            new_name = storage.save(
                old.field.generate_filename(profile, f"{uuid.uuid4().hex}.jpg"), ContentFile(new_bytes)
            )
            # update(), not save(): PilgrimProfile.save() would process the
            # file again, and nothing else on the row should change.
            PilgrimProfile.objects.filter(pk=profile.pk).update(avatar=new_name)
            storage.delete(old_name)
            cleaned += 1

        verb = "Would clean" if options["dry_run"] else "Cleaned"
        self.stdout.write(f"{verb} {cleaned} avatar(s); {skipped} already clean; {failed} failed.")
