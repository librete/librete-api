"""Delivery of due event reminders over Web Push (used by `manage.py send_reminders`)."""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pywebpush
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from .models import PushSubscription, ScheduledReminder

logger = logging.getLogger(__name__)

# Reminders more than this late (e.g. after downtime), or for events that started longer
# ago than this, are marked sent without being delivered.
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


def _zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def build_body(event, user, now):
    """'Starts at 18:00 · NDK', with the date when the event isn't today (user's zone)."""
    zone = _zone(user.time_zone)
    start = event.start_date.astimezone(zone)
    time = start.strftime("%H:%M")
    if start.date() == now.astimezone(zone).date():
        body = _("Starts at {time}").format(time=time)
    else:
        date = formats.date_format(start, "SHORT_DATE_FORMAT")
        body = _("Starts on {date} at {time}").format(date=date, time=time)
    if event.location:
        body = f"{body} · {event.location}"
    return body


def build_payload(reminder, now):
    """The push message in the format the Angular service worker (`SwPush`) displays."""
    event = reminder.event
    user = event.author
    with translation.override(user.language):
        body = build_body(event, user, now)
    return {
        "notification": {
            "title": event.name,
            "body": body,
            "icon": ICON,
            "badge": BADGE,
            "tag": f"event-{event.id}-{reminder.minutes_before}",
            "data": {
                "eventId": event.id,
                "onActionClick": {
                    "default": {
                        "operation": "navigateLastFocusedOrOpen",
                        "url": f"/events/{event.id}",
                    },
                },
            },
        },
    }


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
        reminders = ScheduledReminder.objects.filter(pk__in=ids).select_related("event__author")
        subscriptions = {}
        used = set()
        for reminder in reminders:
            author_id = reminder.event.author_id
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
    pending = ScheduledReminder.objects.filter(sent_at__isnull=True, remind_at__lte=now)

    stale = pending.filter(Q(remind_at__lt=cutoff) | Q(event__start_date__lt=cutoff))
    result.skipped = stale.update(sent_at=now)
    due = pending.filter(remind_at__gte=cutoff, event__start_date__gte=cutoff)
    while _send_batch(due, now, result):
        pass
    return result
