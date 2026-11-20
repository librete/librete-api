"""Delivery of due event and task reminders over Web Push (`manage.py send_reminders`)."""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta

import pywebpush
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Case, DateTimeField, F, Q, When
from django.db.models.functions import Coalesce
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from librete.utils.recurrence import format_utc, zone

from . import actions
from .models import PushSubscription, ScheduledReminder

logger = logging.getLogger(__name__)

# Reminders more than this late (e.g. after downtime), or for events that started (tasks
# that were due) longer ago than this, are marked sent without being delivered. Snoozed
# (one-off) reminders are only checked for lateness.
GRACE_PERIOD = timedelta(hours=1)
# How long push services keep an undelivered message (the device may be offline).
PUSH_TTL = 60 * 60
PUSH_TIMEOUT = 10
BATCH_SIZE = 100
GONE_STATUSES = {404, 410}

ICON = "/icons/icon-192x192.png"
BADGE = "/icons/icon-96x96.png"

_warned_not_configured = False


@dataclass
class SendResult:
    reminders: int = 0  # reminders processed and marked sent (delivered or not)
    skipped: int = 0  # stale reminders marked sent without delivery
    delivered: int = 0  # successful pushes
    failed: int = 0  # pushes that failed for other reasons
    removed: int = 0  # subscriptions deleted because the push service answered 404/410

    def __bool__(self):
        return any(vars(self).values())


def vapid_configured():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def _when(moment, user, now, today_text, other_day_text):
    """Format `moment` in the user's zone: the time, plus the date if it isn't today."""
    tz = zone(user.time_zone)
    local = moment.astimezone(tz)
    time = local.strftime("%H:%M")
    if local.date() == now.astimezone(tz).date():
        return today_text.format(time=time)
    date = formats.date_format(local, "SHORT_DATE_FORMAT")
    return other_day_text.format(date=date, time=time)


def build_body(event, user, now, start=None):
    """'Starts at 18:00 · NDK', with the date when the event isn't today (user's zone)."""
    body = _when(
        start or event.start_date,
        user,
        now,
        _("Starts at {time}"),
        _("Starts on {date} at {time}"),
    )
    if event.location:
        body = f"{body} · {event.location}"
    return body


def build_task_body(task, user, now):
    """'Due at 18:00 · Home', with the date when the task isn't due today (user's zone)."""
    body = _when(
        task.end_date or task.start_date,
        user,
        now,
        _("Due at {time}"),
        _("Due on {date} at {time}"),
    )
    if task.category_id is not None:
        body = f"{body} · {task.category.name}"
    return body


def _navigate(url):
    return {"operation": "navigateLastFocusedOrOpen", "url": url}


def _send_request(url):
    return {"operation": "sendRequest", "url": url}


def _event_notification(reminder, now):
    event = reminder.event
    user = event.author
    occurrence = reminder.occurrence_start
    start = occurrence or event.start_date
    url = f"/events/{event.id}"
    if occurrence:
        url = f"{url}?occurrence={format_utc(occurrence)}"
    snooze = actions.action_url(
        actions.SNOOZE,
        actions.EVENT,
        event.id,
        user.id,
        minutes=actions.EVENT_SNOOZE_MINUTES,
        occurrence=occurrence,
    )
    return {
        "title": event.name,
        "body": build_body(event, user, now, start),
        "tag": f"event-{event.id}-{int(start.timestamp())}-{reminder.minutes_before}",
        "actions": [{"action": "snooze", "title": _("Snooze 10 min")}],
        "data": {
            "eventId": event.id,
            "occurrenceStart": format_utc(occurrence) if occurrence else None,
            "onActionClick": {"default": _navigate(url), "snooze": _send_request(snooze)},
        },
    }


def _task_notification(reminder, now):
    task = reminder.task
    user = task.author
    done = actions.action_url(actions.DONE, actions.TASK, task.id, user.id)
    snooze = actions.action_url(
        actions.SNOOZE, actions.TASK, task.id, user.id, minutes=actions.TASK_SNOOZE_MINUTES
    )
    return {
        "title": task.name,
        "body": build_task_body(task, user, now),
        "tag": f"task-{task.id}-{reminder.minutes_before}",
        "actions": [
            {"action": "done", "title": _("Mark done")},
            {"action": "snooze", "title": _("Snooze 1 h")},
        ],
        "data": {
            "taskId": task.id,
            "onActionClick": {
                "default": _navigate(f"/tasks/{task.id}"),
                "done": _send_request(done),
                "snooze": _send_request(snooze),
            },
        },
    }


def build_payload(reminder, now):
    """The push message in the format the Angular service worker (`SwPush`) displays."""
    author = (reminder.event or reminder.task).author
    with translation.override(author.language):
        if reminder.event_id is not None:
            notification = _event_notification(reminder, now)
        else:
            notification = _task_notification(reminder, now)
    return {"notification": {"icon": ICON, "badge": BADGE, **notification}}


def push(subscription, payload):
    """Send one message. Returns "ok", "gone" (subscription expired) or "failed"."""
    try:
        pywebpush.webpush(
            subscription_info=subscription.subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            # A new dict every time: pywebpush stores the endpoint's audience in it.
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=PUSH_TTL,
            headers={"Urgency": "high"},
            timeout=PUSH_TIMEOUT,
        )
    except pywebpush.WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in GONE_STATUSES:
            return "gone"
        body = str(getattr(exc.response, "text", "") or "")
        logger.warning(
            "Web Push to subscription %s failed: %s %s",
            subscription.pk,
            status or exc.message,
            body[:200],
        )
        return "failed"
    except Exception:
        logger.exception("Web Push to subscription %s failed", subscription.pk)
        return "failed"
    return "ok"


def _lock(queryset):
    """Lock the selected rows so that concurrent workers never send the same reminder."""
    features = connection.features
    if not features.has_select_for_update:  # SQLite: a single writer anyway
        return queryset
    kwargs = {}
    if features.has_select_for_update_skip_locked:
        kwargs["skip_locked"] = True
    if features.has_select_for_update_of:
        kwargs["of"] = ("self",)
    return queryset.select_for_update(**kwargs)


def _send_batch(due, now, result):
    with transaction.atomic():
        locked = _lock(due.order_by("remind_at", "pk")).values_list("pk", flat=True)
        ids = list(locked[:BATCH_SIZE])
        if not ids:
            return False
        reminders = ScheduledReminder.objects.filter(pk__in=ids).select_related(
            "event__author", "task__author", "task__category"
        )
        subscriptions = {}
        used = set()
        for reminder in reminders:
            author_id = (reminder.event or reminder.task).author_id
            if author_id not in subscriptions:
                subscriptions[author_id] = list(PushSubscription.objects.filter(user_id=author_id))
            payload = build_payload(reminder, now)
            for subscription in list(subscriptions[author_id]):
                outcome = push(subscription, payload)
                if outcome == "ok":
                    result.delivered += 1
                    used.add(subscription.pk)
                elif outcome == "gone":
                    subscription.delete()
                    subscriptions[author_id].remove(subscription)
                    result.removed += 1
                else:
                    result.failed += 1
        PushSubscription.objects.filter(pk__in=used).update(last_used_at=now)
        result.reminders += ScheduledReminder.objects.filter(pk__in=ids).update(sent_at=now)
    return True


def send_due_reminders(now=None):
    """Deliver every due reminder to all Web Push subscriptions of the event's author.

    Does nothing (and logs a warning once) while VAPID keys are not configured.
    """
    global _warned_not_configured
    result = SendResult()
    if not vapid_configured():
        if not _warned_not_configured:
            logger.warning("VAPID keys are not configured; reminders are not sent.")
            _warned_not_configured = True
        return result

    now = now or timezone.now()
    cutoff = now - GRACE_PERIOD
    pending = ScheduledReminder.objects.filter(sent_at__isnull=True, remind_at__lte=now).annotate(
        # When the event / occurrence starts or the task is due (snoozes: the reminder).
        target=Case(
            When(one_off=True, then=F("remind_at")),
            When(occurrence_start__isnull=False, then=F("occurrence_start")),
            When(event__isnull=False, then=F("event__start_date")),
            default=Coalesce(F("task__end_date"), F("task__start_date")),
            output_field=DateTimeField(),
        )
    )

    stale = pending.filter(Q(remind_at__lt=cutoff) | Q(target__lt=cutoff))
    result.skipped = ScheduledReminder.objects.filter(pk__in=stale.values("pk")).update(
        sent_at=now
    )
    due = pending.filter(remind_at__gte=cutoff, target__gte=cutoff)
    while _send_batch(due, now, result):
        pass
    return result
