"""Delete contact messages past their retention window.

    python manage.py purge_contact_messages

The same cleanup already runs after every successful contact-form
submission (ContactMessage.purge_expired); this is for running it on demand.
Prayer requests go after 90 days, spam after 30 days, everything else after
18 months, and IP hashes are blanked after 7 days.
"""
from django.core.management.base import BaseCommand

from contact.models import ContactMessage


class Command(BaseCommand):
    help = "Delete contact messages past their retention window and blank old IP hashes."

    def handle(self, *args, **options):
        deleted, blanked = ContactMessage.purge_expired()
        self.stdout.write(f"Deleted {deleted} message(s); blanked {blanked} IP hash(es).")
