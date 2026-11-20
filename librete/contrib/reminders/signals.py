from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from librete.contrib.events.models import Event
from librete.contrib.tasks.models import Task

from .services import sync_event_reminders, sync_task_reminders

EVENT_FIELDS = {
    "start_date",
    "end_date",
    "reminders",
    "recurrence",
    "exdates",
    "recurrence_parent",
    "original_start",
}
TASK_FIELDS = {"start_date", "end_date", "reminders", "status"}


def _refresh_series(series_id):
    series = Event.objects.filter(pk=series_id).select_related("author").first()
    if series is not None and series.recurrence:
        sync_event_reminders(series)


@receiver(post_save, sender=Event)
def sync_scheduled_reminders(sender, instance, raw=False, update_fields=None, **kwargs):
    # Deleting an event deletes its scheduled reminders (FK cascade).
    if raw:
        return
    if update_fields is not None and not EVENT_FIELDS & set(update_fields):
        return
    sync_event_reminders(instance)
    # An override hides an occurrence of its series: refresh the series' rows.
    if instance.recurrence_parent_id is not None:
        _refresh_series(instance.recurrence_parent_id)


@receiver(post_delete, sender=Event)
def refresh_series_after_override_delete(sender, instance, **kwargs):
    # After commit: when the whole series is being deleted, there is nothing to refresh
    # (and writing rows for it in the middle of the cascade would break it).
    if instance.recurrence_parent_id is not None:
        series_id = instance.recurrence_parent_id
        transaction.on_commit(lambda: _refresh_series(series_id))


@receiver(post_save, sender=Task)
def sync_scheduled_task_reminders(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    if update_fields is not None and not TASK_FIELDS & set(update_fields):
        return
    sync_task_reminders(instance)
