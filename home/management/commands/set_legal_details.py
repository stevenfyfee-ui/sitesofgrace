"""Fill in Settings > Legal details from the console prompt (GO-LIVE step 3).

    python manage.py set_legal_details --dry-run
    python manage.py set_legal_details

The values are typed at the prompt, never passed as arguments, so they don't
end up in shell history, process lists or logs, and they're never printed
back. Press Enter to keep a field's current value. The legal pages use seven
fields: the operator name, contact email and mailing address, and the four
DMCA agent fields on the Copyright & Content Policy page.
"""
import sys

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from wagtail.models import Site

from home.legal import TOKENS
from home.models import LegalDetails

FIELDS = list(TOKENS.values())


class Command(BaseCommand):
    help = "Prompt for the Legal details values and save them (Enter keeps the current value)."
    # Tests pass a fake prompt here; there is no command-line way to supply values.
    stealth_options = ("_input",)

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Prompt, validate and report; save nothing.")

    def handle(self, *args, **options):
        if not sys.stdin.isatty() and not options.get("_input"):
            raise CommandError("Run this in an interactive console: it reads the values from the prompt.")
        ask = options.get("_input") or input
        site = Site.objects.filter(is_default_site=True).first()
        details = LegalDetails.load(request_or_site=site)
        say = self.stdout.write
        say("Type each value and press Enter. Press Enter on its own to keep what's there.")
        say("Values are not echoed back or logged.")
        changed = []
        for name in FIELDS:
            field = details._meta.get_field(name)
            state = "currently set" if str(getattr(details, name) or "").strip() else "currently blank"
            value = ask(f"{str(field.verbose_name).capitalize()} ({state}): ").strip()
            if not value:
                continue
            if "\\n" in value and field.get_internal_type() == "TextField":
                value = value.replace("\\n", "\n")  # addresses: type \n for a new line
            try:
                field.clean(value, details)
            except ValidationError as exc:
                raise CommandError(f"{field.verbose_name}: {' '.join(exc.messages)} Nothing was saved.")
            setattr(details, name, value)
            changed.append(str(field.verbose_name))
        still_blank = [str(details._meta.get_field(n).verbose_name) for n in FIELDS
                       if not str(getattr(details, n) or "").strip()]
        if options["dry_run"]:
            say(f"DRY RUN -- would update: {', '.join(changed) if changed else 'nothing'}")
        elif changed:
            details.save()
            say(self.style.SUCCESS(f"Saved: {', '.join(changed)}"))
        else:
            say("Nothing changed.")
        say(f"Still blank: {', '.join(still_blank) if still_blank else 'none'}")
