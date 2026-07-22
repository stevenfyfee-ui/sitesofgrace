from django import forms

from .models import PilgrimProfile


class PilgrimProfileForm(forms.ModelForm):
    class Meta:
        model = PilgrimProfile
        fields = ["display_name", "avatar", "home_country", "journey_visibility", "newsletter_opt_in"]
