from allauth.account.signals import user_signed_up
from django.dispatch import receiver

from .models import PilgrimProfile


@receiver(user_signed_up)
def create_pilgrim_profile(request, user, **kwargs):
    PilgrimProfile.objects.get_or_create(user=user)
