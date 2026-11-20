"""Keep `ScheduledReminder` rows in line with the reminders of events and tasks.

- A plain event (or an override) gets one row per offset before its `start_date`.
- A series gets rows for its occurrences that start within the rolling window
  [now - GRACE_PERIOD, now + SERIES_WINDOW] (skipping exdates and overridden occurrences).
  Saving the series refreshes them; the worker tops the window up daily.
- A task gets one row per offset before its due date (`end_date`, else `start_date`); none
  without a date or once it is finished.

Rows whose time changed are rescheduled and marked unsent; unchanged rows keep `sent_at`.
`one_off` rows (snoozes) are never touched here.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from librete.contrib.events.models import Event
from librete.contrib.events.recurrence import excluded_starts, overridden_starts
from librete.contrib.tasks.models import Task
from librete.utils import recurrence

from .models import ScheduledReminder, UsedActionToken

# Occurrences of a series starting within this time from now have reminder rows.
SERIES_WINDOW = timedelta(days=60)
# Rows up to this late are still sent (see sender.GRACE_PERIOD), so they are kept.
GRACE_PERIOD = timedelta(hours=1)
# Sent snoozes and used action tokens are deleted after this (tokens expire after 7 days).
RETENTION = timedelta(days=8)


def _apply(existing, desired, make):
    """Make the rows in `existing` ({key: row}) match `desired` ({key: remind_at})."""
    removed = [row.pk for key, row in existing.items() if key not in desired]
    if removed:
        ScheduledReminder.objects.filter(pk__in=removed).delete()
    to_create, to_update = [], []
    for key, remind_at in desired.items():
        row = existing.get(key)
        if row is None:
            to_create.append(make(key, remind_at))
        elif row.remind_at != remind_at:
            row.remind_at = remind_at
            row.sent_at = None
            to_update.append(row)
    if to_create:
        ScheduledReminder.objects.bulk_create(to_create)
    if to_update:
        ScheduledReminder.objects.bulk_update(to_update, ["remind_at", "sent_at"])


def _series_starts(event, now):
    overrides = Event.objects.filter(recurrence_parent=event).only(
        "recurrence_parent_id", "original_start"
    )
    skip = overridden_starts(overrides).get(event.pk, set()) | excluded_starts(event)
    starts = recurrence.starts_between(
        event.recurrence,
        event.start_date,
        recurrence.zone(event.author.time_zone),
        now - GRACE_PERIOD,
        now + SERIES_WINDOW,
    )
    return [start for start in starts if start not in skip]


def sync_event_reminders(event, now=None):
    """Make the event's (non one-off) rows match its reminders, start and recurrence."""
    now = now or timezone.now()
    offsets = set(event.reminders or [])
    if event.recurrence:
        starts = _series_starts(event, now) if offsets else []
        desired = {
            (start, minutes): start - timedelta(minutes=minutes)
            for start in starts
            for minutes in offsets
        }
    else:
        desired = {
            (None, minutes): event.start_date - timedelta(minutes=minutes) for minutes in offsets
        }
    existing = {
        (row.occurrence_start, row.minutes_before): row
        for row in ScheduledReminder.objects.filter(event=event, one_off=False)
    }
    _apply(
        existing,
        desired,
        lambda key, remind_at: ScheduledReminder(
            event=event, occurrence_start=key[0], minutes_before=key[1], remind_at=remind_at
        ),
    )


def sync_task_reminders(task):
    """Make the task's (non one-off) rows match its reminders, due date and status."""
    due = task.end_date or task.start_date
    desired = {}
    if due is not None and task.status != Task.Status.FINISHED:
        desired = {
            minutes: due - timedelta(minutes=minutes) for minutes in set(task.reminders or [])
        }
    existing = {
        row.minutes_before: row
        for row in ScheduledReminder.objects.filter(task=task, one_off=False)
    }
    _apply(
        existing,
        desired,
        lambda minutes, remind_at: ScheduledReminder(
            task=task, minutes_before=minutes, remind_at=remind_at
        ),
    )


def refresh_series_of(user, now=None):
    """Re-derive the reminders of the user's series (e.g. after a time zone change)."""
    for event in Event.objects.filter(author=user, recurrence__isnull=False):
        sync_event_reminders(event, now)


def top_up_series_reminders(now=None):
    """Move every series' reminder window forward; clean up old snoozes and tokens.

    Returns the number of series refreshed.
    """
    now = now or timezone.now()
    count = 0
    series = Event.objects.filter(recurrence__isnull=False).select_related("author")
    for event in series.iterator(chunk_size=200):
        with transaction.atomic():
            sync_event_reminders(event, now)
        count += 1
    ScheduledReminder.objects.filter(one_off=True, sent_at__lt=now - RETENTION).delete()
    UsedActionToken.objects.filter(used_at__lt=now - RETENTION).delete()
    return count
