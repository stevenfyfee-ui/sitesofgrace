from django import forms
from django.utils import timezone

from .models import PilgrimProfile, RESERVED_HANDLES


class AgeConfirmationSignupForm(forms.Form):
    """Merged into allauth's generated signup form via ACCOUNT_SIGNUP_FORM_CLASS."""

    age_confirmed = forms.BooleanField(
        required=True,
        label="I am 13 years of age or older",
    )

    def signup(self, request, user):
        profile, _ = PilgrimProfile.objects.get_or_create(user=user, defaults={"handle": _handle_for(user)})
        profile.age_confirmed_at = timezone.now()
        profile.save(update_fields=["age_confirmed_at"])


def _handle_for(user):
    from .signals import generate_unique_handle

    return generate_unique_handle(user)


class ProfileSettingsForm(forms.ModelForm):
    class Meta:
        model = PilgrimProfile
        fields = [
            "handle",
            "display_name",
            "bio",
            "avatar",
            "home_city",
            "home_country",
            "is_private",
            "dm_policy",
            "public_credit_default",
        ]

    def clean_handle(self):
        handle = self.cleaned_data["handle"].lower()
        if handle in RESERVED_HANDLES:
            raise forms.ValidationError("That handle is reserved. Please choose another.")
        conflict = PilgrimProfile.objects.filter(handle=handle).exclude(pk=self.instance.pk)
        if conflict.exists():
            raise forms.ValidationError("That handle is already taken.")
        return handle
