from django.conf import settings
from django.db import models
from django.utils import timezone


class PilgrimProfile(models.Model):
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_PUBLIC = "public"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_PUBLIC, "Public"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pilgrim_profile"
    )
    display_name = models.CharField(max_length=120, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    home_country = models.CharField(max_length=120, blank=True)
    journey_visibility = models.CharField(
        max_length=20, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE
    )
    newsletter_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name or self.user.get_username()


class JourneyEntry(models.Model):
    STATUS_SAVED = "saved"
    STATUS_WANT = "want"
    STATUS_VISITED = "visited"
    STATUS_CHOICES = [
        (STATUS_SAVED, "Save to my journey"),
        (STATUS_WANT, "Want to visit"),
        (STATUS_VISITED, "Visited"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journey_entries"
    )
    site = models.ForeignKey(
        "catalog.SacredSitePage", on_delete=models.CASCADE, related_name="journey_entries"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    visited_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "site")

    def __str__(self):
        return f"{self.user} - {self.site} ({self.status})"

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_VISITED and not self.visited_date:
            self.visited_date = timezone.localdate()
        super().save(*args, **kwargs)
