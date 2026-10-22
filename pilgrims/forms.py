from django import forms
from django.utils import timezone

from . import consent
from .models import PilgrimProfile, RESERVED_HANDLES


class AgeConfirmationSignupForm(forms.Form):
    """Merged into allauth's generated signup form via ACCOUNT_SIGNUP_FORM_CLASS."""

    age_confirmed = forms.BooleanField(
        required=True,
        label="I am 13 years of age or older",
    )

    def signup(self, request, user):
        profile, _ = PilgrimProfile.objects.get_or_create(user=user, defaults={"handle": _handle_for(user)})
        now = timezone.now()
        profile.age_confirmed_at = now
        # The sign-up notice above the button says that creating an account
        # agrees to the Terms; record when, and which version was live.
        profile.terms_accepted_at = now
        profile.terms_version = _live_terms_version()
        profile.save(update_fields=["age_confirmed_at", "terms_accepted_at", "terms_version"])


def _handle_for(user):
    from .signals import generate_unique_handle

    return generate_unique_handle(user)


def _live_terms_version():
    """The live Terms of Use page's effective date ("2026-10-22"), or ""."""
    from home.models import LegalPage

    terms = LegalPage.objects.live().public().filter(slug="terms-of-use").first()
    return terms.effective_date.isoformat() if terms else ""


class ProfileSettingsForm(forms.ModelForm):
    # Shown only until the pilgrim has confirmed once (see __init__); the
    # label is the "Legal notices" share_adult_checkbox text, rendered by
    # the template.
    share_adult = forms.BooleanField(required=False, label="I am 18 or older.")

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not consent.needs_adult_confirmation(self.instance):
            del self.fields["share_adult"]
        else:
            # Right under the private-profile toggle it unlocks.
            order = list(self.fields)
            order.remove("share_adult")
            order.insert(order.index("is_private") + 1, "share_adult")
            self.order_fields(order)

    def clean_handle(self):
        handle = self.cleaned_data["handle"].lower()
        if handle in RESERVED_HANDLES:
            raise forms.ValidationError("That handle is reserved. Please choose another.")
        conflict = PilgrimProfile.objects.filter(handle=handle).exclude(pk=self.instance.pk)
        if conflict.exists():
            raise forms.ValidationError("That handle is already taken.")
        return handle

    def clean(self):
        cleaned = super().clean()
        # self.instance still holds the saved values here: ModelForm copies
        # cleaned_data onto it only after clean().
        going_public = self.instance.is_private and cleaned.get("is_private") is False
        if (
            going_public
            and consent.needs_adult_confirmation(self.instance)
            and not cleaned.get("share_adult")
        ):
            self.add_error(
                "share_adult" if "share_adult" in self.fields else None,
                "Please confirm you're 18 or older to make your profile public.",
            )
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit and self.cleaned_data.get("share_adult"):
            consent.record_adult_confirmation(profile)
        return profile
