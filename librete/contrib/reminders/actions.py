"""Signed, single-use, expiring notification action URLs (`GET /api/actions/<token>/`).

The PWA's service worker can't use the login token, so every action of a push notification
carries its own URL. The token is a `django.core.signing` object (salt `librete.actions`)
`{"op", "type", "id", "occurrence", "minutes", "user", "jti"}`; it is valid for 7 days and
its `jti` is stored in `UsedActionToken` when it is used.
"""

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from librete.contrib.events.models import Event
from librete.contrib.events.recurrence import parse_utc
from librete.contrib.tasks.models import Task
from librete.utils.models import lock_owner
from librete.utils.recurrence import format_utc

from .models import ScheduledReminder, UsedActionToken

SALT = "librete.actions"
MAX_AGE = timedelta(days=7)
DONE, SNOOZE = "done", "snooze"
EVENT, TASK = "event", "task"
EVENT_SNOOZE_MINUTES = 10
TASK_SNOOZE_MINUTES = 60
MAX_SNOOZE_MINUTES = 7 * 24 * 60


class ActionError(Exception):
    """The token is unusable: `status` is 400 (malformed/tampered) or 410 (gone)."""

    def __init__(self, status):
        super().__init__(status)
        self.status = status


def make_token(op, type, id, user_id, minutes=0, occurrence=None):
    return signing.dumps(
        {
            "op": op,
            "type": type,
            "id": id,
            "occurrence": format_utc(occurrence) if occurrence else None,
            "minutes": minutes,
            "user": user_id,
            "jti": str(uuid.uuid4()),
        },
        salt=SALT,
    )


def action_url(*args, **kwargs):
    return f"/api/actions/{make_token(*args, **kwargs)}/"


def _load(token):
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.SignatureExpired:
        raise ActionError(410) from None
    except signing.BadSignature:
        raise ActionError(400) from None
    try:
        valid = (
            data["op"] in (DONE, SNOOZE)
            and data["type"] in (EVENT, TASK)
            and not (data["op"] == DONE and data["type"] != TASK)
            and isinstance(data["id"], int)
            and isinstance(data["user"], int)
            and isinstance(data["minutes"], int)
            and (data["op"] != SNOOZE or 1 <= data["minutes"] <= MAX_SNOOZE_MINUTES)
        )
        jti = uuid.UUID(data["jti"])
        occurrence = parse_utc(data["occurrence"]) if data["occurrence"] else None
    except (KeyError, TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise ActionError(400)
    return data, jti, occurrence


def perform(token, now=None):
    """Carry out the action; raises `ActionError` and changes nothing if it can't."""
    data, jti, occurrence = _load(token)
    now = now or timezone.now()
    user = get_user_model().objects.filter(pk=data["user"]).first()
    if user is None:
        raise ActionError(410)
    with transaction.atomic():
        lock_owner(user.pk)
        model = Task if data["type"] == TASK else Event
        item = model.objects.filter(pk=data["id"], author=user).first()
        if item is None or UsedActionToken.objects.filter(jti=jti).exists():
            raise ActionError(410)
        try:
            with transaction.atomic():
                UsedActionToken.objects.create(jti=jti)
        except IntegrityError:
            raise ActionError(410) from None

        if data["op"] == DONE:
            if item.status != Task.Status.FINISHED:
                item.status = Task.Status.FINISHED
                item.save()  # versioned, logged, creates the next repeat instance
        else:
            ScheduledReminder.objects.create(
                event=item if model is Event else None,
                task=item if model is Task else None,
                occurrence_start=occurrence,
                minutes_before=0,
                remind_at=now + timedelta(minutes=data["minutes"]),
                one_off=True,
            )
