from allauth.account.signals import user_signed_up
from django.dispatch import receiver

from .services import create_default_categories


@receiver(user_signed_up)
def add_default_categories(sender, request, user, **kwargs):
    create_default_categories(user)
