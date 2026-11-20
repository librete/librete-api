import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
import time_machine
from django.core import signing
from django.core.management import call_command
from pywebpush import WebPushException

from librete.contrib.reminders import sender
from librete.contrib.reminders.management.commands.send_reminders import run_forever
from librete.contrib.reminders.models import PushSubscription, ScheduledReminder, WorkerRun
from librete.tests.factories import EventFactory, PushSubscriptionFactory, UserFactory

NOW = datetime(2030, 5, 1, 17, 45, tzinfo=UTC)
START = datetime(2030, 5, 1, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def vapid(settings, monkeypatch):
    settings.VAPID_PUBLIC_KEY = "BPublicKey"
    settings.VAPID_PRIVATE_KEY = "private-key"
    settings.VAPID_SUBJECT = "mailto:admin@example.com"
    monkeypatch.setattr(sender, "_warned_not_configured", False)


@pytest.fixture
def webpush():
    with mock.patch("pywebpush.webpush") as patched:
        yield patched


def gone(status):
    response = mock.Mock(status_code=status, text="push service says no")
    return WebPushException("Push failed", response=response)


def pushed(webpush):
    """[(endpoint, payload)] for every webpush call."""
    return [
        (call.kwargs["subscription_info"]["endpoint"], json.loads(call.kwargs["data"]))
        for call in webpush.call_args_list
    ]


def tag(event, minutes, start=None):
    return f"event-{event.id}-{int((start or event.start_date).timestamp())}-{minutes}"


def sent_at(event, minutes_before):
    return ScheduledReminder.objects.get(event=event, minutes_before=minutes_before).sent_at


@pytest.mark.django_db
def test_only_due_reminders_are_sent(webpush):
    event = EventFactory(name="Concert", start_date=START, reminders=[60, 15, 5])
    subscription = PushSubscriptionFactory(user=event.author)
    ScheduledReminder.objects.filter(minutes_before=60).update(sent_at=NOW - timedelta(minutes=45))

    result = sender.send_due_reminders(now=NOW)

    # 60: already sent, 15: due exactly now, 5: still in the future.
    assert [(endpoint, p["notification"]["tag"]) for endpoint, p in pushed(webpush)] == [
        (subscription.endpoint, tag(event, 15))
    ]
    assert sent_at(event, 60) == NOW - timedelta(minutes=45)
    assert sent_at(event, 15) == NOW
    assert sent_at(event, 5) is None
    assert (result.reminders, result.delivered, result.skipped) == (1, 1, 0)

    webpush.reset_mock()
    assert not sender.send_due_reminders(now=NOW)
    webpush.assert_not_called()


@pytest.mark.django_db
def test_stale_reminders_are_marked_sent_without_sending(webpush):
    # Due 61 minutes ago (e.g. the worker was down): skipped. Due 60 minutes ago: sent.
    late = EventFactory(start_date=NOW + timedelta(hours=1), reminders=[121, 120])
    PushSubscriptionFactory(user=late.author)
    # An event that started two hours ago.
    past = EventFactory(start_date=NOW - timedelta(hours=2), reminders=[0])
    PushSubscriptionFactory(user=past.author)

    result = sender.send_due_reminders(now=NOW)

    assert [p["notification"]["tag"] for _, p in pushed(webpush)] == [tag(late, 120)]
    assert sent_at(late, 121) == NOW
    assert sent_at(late, 120) == NOW
    assert sent_at(past, 0) == NOW
    assert (result.reminders, result.skipped, result.delivered) == (1, 2, 1)


@pytest.mark.django_db
def test_sends_to_every_subscription_of_the_author_only(webpush):
    event = EventFactory(start_date=START, reminders=[15])
    phone = PushSubscriptionFactory(user=event.author)
    laptop = PushSubscriptionFactory(user=event.author)
    PushSubscriptionFactory(user=UserFactory())

    sender.send_due_reminders(now=NOW)

    assert sorted(endpoint for endpoint, _ in pushed(webpush)) == sorted(
        [phone.endpoint, laptop.endpoint]
    )
    for subscription in (phone, laptop):
        subscription.refresh_from_db()
        assert subscription.last_used_at == NOW


@pytest.mark.django_db
def test_webpush_options(webpush):
    event = EventFactory(start_date=START, reminders=[15])
    subscription = PushSubscriptionFactory(user=event.author)

    sender.send_due_reminders(now=NOW)

    kwargs = webpush.call_args.kwargs
    assert kwargs["subscription_info"] == {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    assert kwargs["vapid_private_key"] == "private-key"
    assert kwargs["vapid_claims"] == {"sub": "mailto:admin@example.com"}
    assert kwargs["ttl"] == 3600
    assert kwargs["headers"] == {"Urgency": "high"}


@pytest.mark.django_db
def test_expired_subscriptions_are_removed_and_errors_do_not_stop_sending(webpush, caplog):
    event = EventFactory(start_date=START, reminders=[15])
    expired = PushSubscriptionFactory(user=event.author)
    unknown = PushSubscriptionFactory(user=event.author)
    erroring = PushSubscriptionFactory(user=event.author)
    offline = PushSubscriptionFactory(user=event.author)
    working = PushSubscriptionFactory(user=event.author)
    outcomes = {
        expired.endpoint: gone(410),
        unknown.endpoint: gone(404),
        erroring.endpoint: gone(500),
        offline.endpoint: ConnectionError("network down"),
    }

    def fake_webpush(subscription_info, **kwargs):
        if error := outcomes.get(subscription_info["endpoint"]):
            raise error

    webpush.side_effect = fake_webpush
    with caplog.at_level(logging.WARNING):
        result = sender.send_due_reminders(now=NOW)

    assert webpush.call_count == 5
    assert set(PushSubscription.objects.values_list("pk", flat=True)) == {
        erroring.pk,
        offline.pk,
        working.pk,
    }
    assert sent_at(event, 15) == NOW
    assert (result.delivered, result.failed, result.removed) == (1, 2, 2)
    assert PushSubscription.objects.get(pk=working.pk).last_used_at == NOW
    assert PushSubscription.objects.get(pk=erroring.pk).last_used_at is None
    assert "failed" in caplog.text


@pytest.mark.django_db
def test_an_expired_subscription_is_not_used_again_in_the_same_run(webpush):
    event = EventFactory(start_date=START, reminders=[30, 15])
    PushSubscriptionFactory(user=event.author)
    webpush.side_effect = gone(410)

    sender.send_due_reminders(now=NOW)

    assert webpush.call_count == 1
    assert not PushSubscription.objects.exists()
    assert ScheduledReminder.objects.filter(sent_at=NOW).count() == 2


@pytest.mark.django_db
def test_reminders_without_subscriptions_are_marked_sent(webpush):
    event = EventFactory(start_date=START, reminders=[15])
    result = sender.send_due_reminders(now=NOW)
    webpush.assert_not_called()
    assert sent_at(event, 15) == NOW
    assert result.reminders == 1


@pytest.mark.django_db
def test_payload_format(webpush):
    event = EventFactory(name="Concert", location="NDK", start_date=START, reminders=[15])
    PushSubscriptionFactory(user=event.author)

    sender.send_due_reminders(now=NOW)

    payload = pushed(webpush)[0][1]
    snooze_url = payload["notification"]["data"]["onActionClick"]["snooze"]["url"]
    assert payload == {
        "notification": {
            "title": "Concert",
            "body": "Starts at 18:00 · NDK",
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/icon-96x96.png",
            "tag": f"event-{event.id}-{int(START.timestamp())}-15",
            "actions": [{"action": "snooze", "title": "Snooze 10 min"}],
            "data": {
                "eventId": event.id,
                "occurrenceStart": None,
                "onActionClick": {
                    "default": {
                        "operation": "navigateLastFocusedOrOpen",
                        "url": f"/events/{event.id}",
                    },
                    "snooze": {"operation": "sendRequest", "url": snooze_url},
                },
            },
        },
    }
    token = snooze_url.removeprefix("/api/actions/").removesuffix("/")
    data = signing.loads(token, salt="librete.actions")
    assert data == {
        "op": "snooze",
        "type": "event",
        "id": event.id,
        "occurrence": None,
        "minutes": 10,
        "user": event.author_id,
        "jti": data["jti"],
    }


@pytest.mark.django_db
def test_payload_includes_the_date_when_the_event_is_not_today(webpush):
    event = EventFactory(location="", start_date=START + timedelta(days=1), reminders=[1440])
    PushSubscriptionFactory(user=event.author)

    sender.send_due_reminders(now=NOW + timedelta(minutes=15))

    assert pushed(webpush)[0][1]["notification"]["body"] == "Starts on 05/02/2030 at 18:00"


@pytest.mark.django_db
def test_payload_is_localized_and_uses_the_users_time_zone(webpush):
    user = UserFactory(language="bg", time_zone="Europe/Sofia")
    # 22:30 UTC on 1 May is 01:30 on 2 May in Sofia (UTC+3): not "today" there at 20:45.
    late = EventFactory(
        author=user,
        name="Концерт",
        location="НДК",
        start_date=START.replace(hour=22, minute=30),
        reminders=[285],
    )
    today = EventFactory(author=user, location="", start_date=START, reminders=[15])
    PushSubscriptionFactory(user=user)

    sender.send_due_reminders(now=NOW)

    notifications = {p["notification"]["tag"]: p["notification"] for _, p in pushed(webpush)}
    assert notifications[tag(late, 285)]["title"] == "Концерт"
    assert notifications[tag(late, 285)]["body"] == "Започва на 02.05.2030 в 01:30 · НДК"
    assert notifications[tag(late, 285)]["actions"] == [
        {"action": "snooze", "title": "Отложи с 10 мин"}
    ]
    assert notifications[tag(today, 15)]["body"] == "Започва в 21:00"


@pytest.mark.django_db
def test_nothing_is_sent_or_marked_without_vapid_keys(webpush, settings, caplog):
    settings.VAPID_PRIVATE_KEY = ""
    event = EventFactory(start_date=START, reminders=[15])
    PushSubscriptionFactory(user=event.author)

    with caplog.at_level(logging.WARNING):
        assert not sender.send_due_reminders(now=NOW)
        sender.send_due_reminders(now=NOW)

    webpush.assert_not_called()
    assert sent_at(event, 15) is None
    assert caplog.text.count("VAPID keys are not configured") == 1


@pytest.mark.django_db
def test_send_reminders_command(webpush):
    event = EventFactory(start_date=START, reminders=[15])
    PushSubscriptionFactory(user=event.author)

    with time_machine.travel(NOW + timedelta(seconds=30), tick=False):
        call_command("send_reminders")

    assert webpush.call_count == 1
    assert sent_at(event, 15) == NOW + timedelta(seconds=30)
    # The command also ran the series top-up and remembered when.
    assert WorkerRun.objects.get(name="series-reminders").last_run_at == NOW + timedelta(
        seconds=30
    )


@pytest.fixture
def no_top_up():
    # run_forever closes old connections, which ends the test's connection on PostgreSQL.
    with mock.patch(
        "librete.contrib.reminders.management.commands.send_reminders.top_up_if_due"
    ) as patched:
        yield patched


@pytest.mark.django_db
def test_loop_runs_until_stopped(no_top_up):
    stop = threading.Event()
    with mock.patch(
        "librete.contrib.reminders.management.commands.send_reminders.send_due_reminders",
        side_effect=lambda: stop.set() or sender.SendResult(),
    ) as send:
        run_forever(interval=0, stop=stop)
    assert send.call_count == 1
    assert no_top_up.call_count == 1


@pytest.mark.django_db
def test_loop_survives_errors(no_top_up):
    stop = threading.Event()
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database restarting")
        stop.set()
        return sender.SendResult()

    with mock.patch(
        "librete.contrib.reminders.management.commands.send_reminders.send_due_reminders",
        side_effect=flaky,
    ):
        run_forever(interval=0, stop=stop)
    assert len(calls) == 2
