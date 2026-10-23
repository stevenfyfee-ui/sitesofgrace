"""
Messages sent through the Contact page (home.ContactPage).

Every message is saved here first, then a staff alert is emailed
(contact/notify.py). Nothing is ever sent to the sender. Rows are read only
in the Wagtail admin "Messages" inbox (superusers only); no public view, API,
or search index ever exposes them.

Retention runs without a scheduled job: purge_expired() is called after every
successful submission (and by `manage.py purge_contact_messages`). The windows
below are the ones the Privacy Policy states (legal/content/privacy-policy.md,
"How long we keep information") -- change one only together with the policy.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# Prayer requests: 90 days.
PRAYER_RETENTION_DAYS = 90
# Every other message: 18 months.
MESSAGE_RETENTION_DAYS = 548
# Messages saved as spam: 30 days.
SPAM_RETENTION_DAYS = 30
# The salted IP hash used to stop form spam: 7 days, then blanked.
IP_HASH_RETENTION_DAYS = 7

# Stable keys, in display order. They're stored and used in URLs
# (?topic=correction): never rename one.
TOPIC_CHOICES = [
    ("question", "Ask a question"),
    ("suggest", "Suggest a sacred site"),
    ("correction", "Submit a correction"),
    ("pilgrimage", "Plan a pilgrimage"),
    ("partner", "Partnerships & press"),
    ("prayer", "Prayer request"),
    ("billing", "Support gifts & billing"),
    ("other", "Something else"),
]
TOPIC_KEYS = [key for key, _ in TOPIC_CHOICES]
DEFAULT_TOPIC = "question"

# Topics whose form shows the "Which site or saint?" picker.
RELATED_TOPICS = ("question", "suggest", "correction", "pilgrimage")

# The message box's label and placeholder per topic, and the picker's help
# line -- rendered server-side for the selected topic and handed to
# contact.js as JSON for the rest. Copied from the mockup.
TOPIC_COPY = {
    "question": {
        "label": "Your question",
        "placeholder": "What would you like to know?",
        "help": "Linking the page helps us find it quickly.",
    },
    "suggest": {
        "label": "Tell us about the place",
        "placeholder": "Name, location, and why it matters. A link to the shrine or diocese helps.",
        "help": "If it relates to a saint we already cover, link them here.",
    },
    "correction": {
        "label": "What's not right?",
        "placeholder": "What the page says, what it should say, and your source if you have one.",
        "help": "Pick the page that needs the correction.",
    },
    "pilgrimage": {
        "label": "Tell us about your trip",
        "placeholder": "Where, roughly when, and how many in your group.",
        "help": "Link any sites you hope to visit.",
    },
    "partner": {
        "label": "Your message",
        "placeholder": "Who you are, your organization, and what you have in mind.",
        "help": "",
    },
    "prayer": {
        "label": "Your intention",
        "placeholder": "Share as much or as little as you like.",
        "help": "",
    },
    "billing": {
        "label": "Your message",
        "placeholder": "Your question about a gift or a monthly support charge. Please don't include card numbers.",
        "help": "",
    },
    "other": {
        "label": "Your message",
        "placeholder": "How can we help?",
        "help": "",
    },
}

MESSAGE_MAX_LENGTH = 5000


class ContactMessage(models.Model):
    STATUS_NEW = "new"
    STATUS_REPLIED = "replied"
    STATUS_CLOSED = "closed"
    STATUS_SPAM = "spam"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REPLIED, "Replied"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_SPAM, "Spam"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    topic = models.CharField(max_length=20, choices=TOPIC_CHOICES, db_index=True)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    related_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    message = models.TextField(max_length=MESSAGE_MAX_LENGTH)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True,
    )
    staff_note = models.TextField(blank=True, help_text="For staff only. Never shown publicly.")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Set when the sender was signed in.",
    )
    # A salted hash (pilgrims.views._ip_hash), never the raw address. Used
    # only for the hourly rate limit, and blanked after IP_HASH_RETENTION_DAYS.
    ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "message"
        verbose_name_plural = "messages"

    def __str__(self):
        return f"{self.get_topic_display()}: {self.name}"

    @property
    def is_prayer(self):
        return self.topic == "prayer"

    @classmethod
    def purge_expired(cls, now=None):
        """Delete messages past their retention window and blank old IP
        hashes. Returns (deleted, hashes_blanked)."""
        now = now or timezone.now()
        prayer_cutoff = now - timedelta(days=PRAYER_RETENTION_DAYS)
        message_cutoff = now - timedelta(days=MESSAGE_RETENTION_DAYS)
        spam_cutoff = now - timedelta(days=SPAM_RETENTION_DAYS)
        deleted, _ = cls.objects.filter(
            models.Q(topic="prayer", created_at__lt=prayer_cutoff)
            | models.Q(status=cls.STATUS_SPAM, created_at__lt=spam_cutoff)
            | models.Q(created_at__lt=message_cutoff)
        ).delete()
        blanked = cls.objects.filter(
            created_at__lt=now - timedelta(days=IP_HASH_RETENTION_DAYS),
        ).exclude(ip_hash="").update(ip_hash="")
        return deleted, blanked
