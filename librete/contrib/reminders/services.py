from datetime import timedelta

from .models import ScheduledReminder


def sync_event_reminders(event):
    """Make `event.scheduled_reminders` match `event.reminders` and `event.start_date`.

    Rows for removed offsets are deleted, new offsets get a row, and rows whose
    `remind_at` moved (start date changed) are rescheduled and marked unsent again.
    """
    desired = {
        minutes: event.start_date - timedelta(minutes=minutes)
        for minutes in set(event.reminders or [])
    }
    existing = {r.minutes_before: r for r in ScheduledReminder.objects.filter(event=event)}

    removed = [r.pk for minutes, r in existing.items() if minutes not in desired]
    if removed:
        ScheduledReminder.objects.filter(pk__in=removed).delete()

    to_create, to_update = [], []
    for minutes, remind_at in desired.items():
        reminder = existing.get(minutes)
        if reminder is None:
            to_create.append(
                ScheduledReminder(event=event, minutes_before=minutes, remind_at=remind_at)
            )
        elif reminder.remind_at != remind_at:
            reminder.remind_at = remind_at
            reminder.sent_at = None
            to_update.append(reminder)
    if to_create:
        ScheduledReminder.objects.bulk_create(to_create)
    if to_update:
        ScheduledReminder.objects.bulk_update(to_update, ["remind_at", "sent_at"])
