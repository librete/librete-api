from django.db.models.signals import post_save
from django.dispatch import receiver

from librete.contrib.events.models import Event

from .services import sync_event_reminders


@receiver(post_save, sender=Event)
def sync_scheduled_reminders(sender, instance, raw=False, update_fields=None, **kwargs):
    # Deleting an event deletes its scheduled reminders (FK cascade).
    if raw:
        return
    if update_fields is not None and not {"start_date", "reminders"} & set(update_fields):
        return
    sync_event_reminders(instance)
