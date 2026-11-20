"""Push payloads of task reminders, series occurrences and snoozes."""

import json
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
import time_machine
from django.core import signing

from librete.contrib.reminders import sender
from librete.contrib.reminders.models import ScheduledReminder
from librete.tests.factories import (
    CategoryFactory,
    EventFactory,
    PushSubscriptionFactory,
    TaskFactory,
    UserFactory,
)

NOW = datetime(2030, 5, 1, 17, 45, tzinfo=UTC)
DUE = datetime(2030, 5, 1, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def vapid(settings, monkeypatch):
    settings.VAPID_PUBLIC_KEY = "BPublicKey"
    settings.VAPID_PRIVATE_KEY = "private-key"
    monkeypatch.setattr(sender, "_warned_not_configured", False)


@pytest.fixture
def webpush():
    with mock.patch("pywebpush.webpush") as patched:
        yield patched


def notifications(webpush):
    return [json.loads(call.kwargs["data"])["notification"] for call in webpush.call_args_list]


def token_of(url):
    assert url.startswith("/api/actions/") and url.endswith("/")
    return signing.loads(url[len("/api/actions/") : -1], salt="librete.actions")


@pytest.mark.django_db
def test_task_payload(webpush):
    category = CategoryFactory(name="Home")
    task = TaskFactory(
        author=category.author, category=category, name="Pay rent", end_date=DUE, reminders=[15]
    )
    PushSubscriptionFactory(user=task.author)

    sender.send_due_reminders(now=NOW)

    [notification] = notifications(webpush)
    click = notification["data"]["onActionClick"]
    assert notification == {
        "title": "Pay rent",
        "body": "Due at 18:00 · Home",
        "icon": "/icons/icon-192x192.png",
        "badge": "/icons/icon-96x96.png",
        "tag": f"task-{task.id}-15",
        "actions": [
            {"action": "done", "title": "Mark done"},
            {"action": "snooze", "title": "Snooze 1 h"},
        ],
        "data": {
            "taskId": task.id,
            "onActionClick": {
                "default": {"operation": "navigateLastFocusedOrOpen", "url": f"/tasks/{task.id}"},
                "done": {"operation": "sendRequest", "url": click["done"]["url"]},
                "snooze": {"operation": "sendRequest", "url": click["snooze"]["url"]},
            },
        },
    }
    done, snooze = token_of(click["done"]["url"]), token_of(click["snooze"]["url"])
    assert {k: done[k] for k in ("op", "type", "id", "occurrence", "user")} == {
        "op": "done",
        "type": "task",
        "id": task.id,
        "occurrence": None,
        "user": task.author_id,
    }
    assert (snooze["op"], snooze["type"], snooze["minutes"]) == ("snooze", "task", 60)
    assert done["jti"] != snooze["jti"]


@pytest.mark.django_db
def test_task_body_with_a_date_and_in_bulgarian(webpush):
    user = UserFactory(language="bg", time_zone="Europe/Sofia")
    category = CategoryFactory(author=user, name="Дом")
    task = TaskFactory(
        author=user,
        category=category,
        name="Наем",
        start_date=DUE + timedelta(days=1),
        reminders=[1440],
    )
    PushSubscriptionFactory(user=user)
    english = TaskFactory(start_date=DUE + timedelta(days=1), reminders=[1440])
    PushSubscriptionFactory(user=english.author)

    sender.send_due_reminders(now=NOW + timedelta(minutes=15))

    by_tag = {n["tag"]: n for n in notifications(webpush)}
    bulgarian = by_tag[f"task-{task.id}-1440"]
    assert bulgarian["body"] == "Срок на 02.05.2030 в 21:00 · Дом"
    assert bulgarian["actions"] == [
        {"action": "done", "title": "Отбележи като готова"},
        {"action": "snooze", "title": "Отложи с 1 ч"},
    ]
    assert by_tag[f"task-{english.id}-1440"]["body"] == (
        f"Due on 05/02/2030 at 18:00 · {english.category.name}"
    )


@pytest.mark.django_db
def test_occurrence_payload(webpush):
    user = UserFactory()
    with time_machine.travel(NOW - timedelta(days=3), tick=False):
        event = EventFactory(
            author=user,
            name="Standup",
            location="",
            start_date=DUE - timedelta(days=7),
            end_date=DUE - timedelta(days=7) + timedelta(minutes=15),
            recurrence="FREQ=DAILY",
            reminders=[15],
        )
    PushSubscriptionFactory(user=user)

    sender.send_due_reminders(now=NOW)

    [notification] = notifications(webpush)
    epoch = int(DUE.timestamp())
    assert notification["tag"] == f"event-{event.id}-{epoch}-15"
    assert notification["body"] == "Starts at 18:00"
    assert notification["data"]["eventId"] == event.id
    assert notification["data"]["occurrenceStart"] == "2030-05-01T18:00:00Z"
    click = notification["data"]["onActionClick"]
    assert click["default"]["url"] == f"/events/{event.id}?occurrence=2030-05-01T18:00:00Z"
    snooze = token_of(click["snooze"]["url"])
    assert (snooze["type"], snooze["id"], snooze["occurrence"], snooze["minutes"]) == (
        "event",
        event.id,
        "2030-05-01T18:00:00Z",
        10,
    )


@pytest.mark.django_db
def test_staleness_uses_the_occurrence_start_due_date_and_snooze_time(webpush):
    user = UserFactory()
    PushSubscriptionFactory(user=user)
    with time_machine.travel(NOW - timedelta(days=3), tick=False):
        series = EventFactory(
            author=user,
            start_date=DUE - timedelta(days=30),  # the series started long ago
            end_date=DUE - timedelta(days=30, minutes=-15),
            recurrence="FREQ=DAILY",
            reminders=[15],
        )
    overdue = TaskFactory(author=user, end_date=NOW - timedelta(hours=2), reminders=[0])
    # Snoozing an overdue task's reminder still delivers it.
    snoozed = ScheduledReminder.objects.create(
        task=overdue, minutes_before=0, remind_at=NOW, one_off=True
    )

    result = sender.send_due_reminders(now=NOW)

    tags = sorted(n["tag"] for n in notifications(webpush))
    assert tags == sorted([f"event-{series.id}-{int(DUE.timestamp())}-15", f"task-{overdue.id}-0"])
    snoozed.refresh_from_db()
    assert snoozed.sent_at == NOW
    stale = ScheduledReminder.objects.get(task=overdue, one_off=False)
    assert stale.sent_at == NOW
    # The occurrences of the three previous days and the overdue task's own reminder.
    assert result.skipped == 4
