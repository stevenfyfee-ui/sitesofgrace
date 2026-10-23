"""
The Contact page form, and the spam signals checked before it's trusted.

The form never sends mail to the address a visitor types: `email` is only
ever used as the Reply-To of the staff alert (contact/notify.py).
"""
import re

from django import forms
from django.core import signing
from wagtail.models import Page

from catalog.models import SacredSitePage, SaintPage

from .models import DEFAULT_TOPIC, MESSAGE_MAX_LENGTH, TOPIC_CHOICES

# The form's render-time token (a TimestampSigner value). A submission
# faster than MIN or older than MAX is treated as spam.
TS_SALT = "contact.form.ts"
TS_MIN_SECONDS = 3
TS_MAX_SECONDS = 24 * 60 * 60

# More links than this in one message is treated as spam.
MAX_URLS = 3
_URL_RE = re.compile(r"(https?://|www\.)", re.I)

HONEYPOT_FIELD = "website"
TURNSTILE_FIELD = "cf-turnstile-response"


def issue_ts():
    return signing.TimestampSigner(salt=TS_SALT).sign("contact")


def ts_is_suspicious(token):
    """True when the token is missing, tampered with, too young, or too old."""
    if not token:
        return True
    signer = signing.TimestampSigner(salt=TS_SALT)
    try:
        signer.unsign(token, max_age=TS_MAX_SECONDS)
    except signing.BadSignature:  # SignatureExpired is a subclass
        return True
    try:
        signer.unsign(token, max_age=TS_MIN_SECONDS)
    except signing.SignatureExpired:
        return False
    return True


def too_many_urls(text):
    return len(_URL_RE.findall(text or "")) > MAX_URLS


def allowed_related_page(value):
    """The live, public SacredSitePage or SaintPage with this id, or None
    for anything else -- never an error."""
    try:
        page_id = int(value)
    except (TypeError, ValueError):
        return None
    if page_id <= 0:
        return None
    return (
        Page.objects.live().public().type(SacredSitePage, SaintPage)
        .filter(pk=page_id).specific().first()
    )


class ContactForm(forms.Form):
    name = forms.CharField(
        label="Your name", max_length=120,
        error_messages={"required": "Please tell us your name."},
        widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "John Doe"}),
    )
    email = forms.EmailField(
        label="Email address",
        error_messages={
            "required": "We'll need a valid email address to reply.",
            "invalid": "We'll need a valid email address to reply.",
        },
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "john.doe@example.com"}),
    )
    topic = forms.ChoiceField(label="What is this about?", choices=TOPIC_CHOICES, initial=DEFAULT_TOPIC)
    related_page = forms.CharField(required=False, widget=forms.HiddenInput)
    message = forms.CharField(
        label="Your message", max_length=MESSAGE_MAX_LENGTH,
        error_messages={
            "required": "Please add a short message.",
            "max_length": "Please keep your message under 5,000 characters.",
        },
        widget=forms.Textarea(attrs={"rows": 7}),
    )
    # Honeypot: off-screen, so only a bot fills it in.
    website = forms.CharField(
        required=False, label="Leave this field empty",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )
    ts = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_related_page(self):
        page = allowed_related_page(self.cleaned_data.get("related_page"))
        return page

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_message(self):
        return self.cleaned_data["message"].strip()
