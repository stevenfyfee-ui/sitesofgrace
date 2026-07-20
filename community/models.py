from django.conf import settings
from django.db import models


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
    home_country = models.CharField(max_length=120, blank=True)
    journey_visibility = models.CharField(
        max_length=20, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE
    )
    newsletter_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name or self.user.get_username()
