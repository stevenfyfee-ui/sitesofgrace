"""
A lazy handle onto the "pilgrim_private" entry in settings.STORAGES.

Two things FileField/ImageField's `storage=` kwarg does NOT do, both of
which bit the first version of this file:

1. It does NOT resolve a bare string alias (a common misconception — only
   the "default" storage gets that treatment, via Django's built-in
   `default_storage` LazyObject). Passing storage="pilgrim_private"
   silently leaves the field's `.storage` attribute as the literal string
   "pilgrim_private", which blows up the first time anything calls
   `.save()`/`.url()`/`.delete()` on the field.

2. If you instead pass a Storage instance directly (e.g. this module's
   LazyObject), `makemigrations` serializes that RESOLVED instance into the
   migration file — every OPTIONS kwarg spelled out literally, including
   access_key/secret_key. In this repo those happen to be empty strings
   today, but the moment SPACES_PRIVATE_KEY/SPACES_PRIVATE_SECRET are set in
   whatever environment next runs makemigrations, the real
   sitesofgrace-pilgrims credentials would be written into a migration file
   and committed to git.

The fix for both: pass a plain module-level CALLABLE. Field.__init__ calls
it once (its return value — this module's LazyObject — becomes the field's
live, working storage), but keeps the ORIGINAL CALLABLE for deconstruct(),
so migrations serialize a stable, secret-free import path
("pilgrims.storage.get_pilgrim_private_storage") instead of a frozen
snapshot of the resolved storage's constructor arguments.

The LazyObject wrapper (rather than a plain resolved Storage instance) also
means `override_settings(STORAGES=...)` in tests actually takes effect —
see the setting_changed receiver below, which mirrors what
django/test/signals.py does for default_storage/staticfiles_storage.
"""
from django.core.files.storage import storages
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.functional import LazyObject, empty


class _PilgrimPrivateStorage(LazyObject):
    def _setup(self):
        self._wrapped = storages["pilgrim_private"]


pilgrim_private_storage = _PilgrimPrivateStorage()


def get_pilgrim_private_storage():
    """Pass THIS (not pilgrim_private_storage directly) to storage=."""
    return pilgrim_private_storage


@receiver(setting_changed)
def _reset_pilgrim_private_storage(*, setting, **kwargs):
    if setting == "STORAGES":
        pilgrim_private_storage._wrapped = empty
