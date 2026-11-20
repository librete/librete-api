from datetime import UTC, datetime, timedelta

import pytest
import time_machine

from librete.contrib.reminders.management.commands.send_reminders import (
    TOP_UP,
    top_up_if_due,
)
from librete.contrib.reminders.models import ScheduledReminder, UsedActionToken, WorkerRun
from librete.contrib.reminders.services import top_up_series_reminders
from librete.tests.factories import EventFactory, UserFactory

NOW = datetime(2030, 5, 1, 12, 0, tzinfo=UTC)
START = datetime(2030, 5, 1, 9, 0, tzinfo=UTC)  # three hours ago


def occurrence_rows(event):
    return sorted(
        ScheduledReminder.objects.filter(event=event, one_off=False).values_list(
            "occurrence_start", "minutes_before", "remind_at"
        )
    )


def daily(user=None, **kwargs):
    kwargs.setdefault("start_date", START)
    kwargs.setdefault("end_date", kwargs["start_date"] + timedelta(hours=1))
    kwargs.setdefault("reminders", [15])
    return EventFactory(author=user or UserFactory(), recurrence="FREQ=DAILY", **kwargs)


@pytest.mark.django_db
def test_series_get_rows_for_the_next_60_days():
    with time_machine.travel(NOW, tick=False):
        event = daily(reminders=[60, 15])
    rows = occurrence_rows(event)
    starts = sorted({row[0] for row in rows})
    # Today's 09:00 started 3 hours ago (outside the grace hour); the next 60 days follow.
    assert starts[0] == START + timedelta(days=1)
    assert starts[-1] == START + timedelta(days=60)
    assert len(starts) == 60
    assert (START + timedelta(days=1), 15, START + timedelta(days=1, minutes=-15)) in rows
    assert len(rows) == 120
    assert not ScheduledReminder.objects.filter(event=event, occurrence_start__isnull=True)


@pytest.mark.django_db
def test_exdates_overrides_and_dst_in_series_rows():
    user = UserFactory(time_zone="Europe/Sofia")
    with time_machine.travel(NOW, tick=False):
        event = daily(user, exdates=["2030-05-03T09:00:00Z"])
        override = EventFactory(
            author=user,
            category=event.category,
            recurrence_parent=event,
            original_start=START + timedelta(days=3),
            start_date=START + timedelta(days=3, hours=2),
            end_date=START + timedelta(days=3, hours=3),
            reminders=[5],
        )
    starts = {row[0] for row in occurrence_rows(event)}
    assert START + timedelta(days=1) in starts
    assert START + timedelta(days=2) not in starts  # exdate
    assert START + timedelta(days=3) not in starts  # overridden
    assert occurrence_rows(override) == [(None, 5, START + timedelta(days=3, hours=2, minutes=-5))]


@pytest.mark.django_db
def test_deleting_an_override_brings_the_occurrence_rows_back(
    django_capture_on_commit_callbacks,
):
    user = UserFactory()
    with time_machine.travel(NOW, tick=False):
        event = daily(user)
        override = EventFactory(
            author=user,
            category=event.category,
            recurrence_parent=event,
            original_start=START + timedelta(days=1),
            reminders=[],
        )
        assert START + timedelta(days=1) not in {row[0] for row in occurrence_rows(event)}
        with django_capture_on_commit_callbacks(execute=True):
            override.delete()
        assert START + timedelta(days=1) in {row[0] for row in occurrence_rows(event)}
        with django_capture_on_commit_callbacks(execute=True):
            event.delete()  # its override callback finds nothing to refresh
    assert not ScheduledReminder.objects.exists()


@pytest.mark.django_db
def test_turning_a_plain_event_into_a_series_and_back():
    with time_machine.travel(NOW, tick=False):
        event = EventFactory(start_date=START + timedelta(days=1), reminders=[15])
        assert occurrence_rows(event) == [(None, 15, START + timedelta(days=1, minutes=-15))]
        event.recurrence = "FREQ=WEEKLY;COUNT=3"
        event.save()
        assert [row[0] for row in occurrence_rows(event)] == [
            START + timedelta(days=1 + 7 * n) for n in range(3)
        ]
        event.recurrence = None
        event.save()
        assert occurrence_rows(event) == [(None, 15, START + timedelta(days=1, minutes=-15))]


@pytest.mark.django_db
def test_top_up_moves_the_window_and_keeps_sent_rows():
    with time_machine.travel(NOW, tick=False):
        event = daily()
    tomorrow = START + timedelta(days=1)
    ScheduledReminder.objects.filter(occurrence_start=tomorrow).update(sent_at=NOW)

    later = NOW + timedelta(days=1)  # 12:00 tomorrow: tomorrow's 09:00 is past
    assert top_up_series_reminders(later) == 1
    starts = sorted(row[0] for row in occurrence_rows(event))
    assert starts[0] == START + timedelta(days=2)
    assert starts[-1] == START + timedelta(days=61)
    assert len(starts) == 60

    ScheduledReminder.objects.filter(occurrence_start=START + timedelta(days=2)).update(
        sent_at=later
    )
    top_up_series_reminders(later + timedelta(minutes=1))
    sent = ScheduledReminder.objects.get(occurrence_start=START + timedelta(days=2))
    assert sent.sent_at == later


@pytest.mark.django_db
def test_top_up_cleans_old_snoozes_and_tokens():
    event = EventFactory(reminders=[])
    old = ScheduledReminder.objects.create(
        event=event, minutes_before=0, remind_at=NOW, sent_at=NOW, one_off=True
    )
    pending = ScheduledReminder.objects.create(
        event=event, minutes_before=0, remind_at=NOW + timedelta(days=9), one_off=True
    )
    with time_machine.travel(NOW, tick=False):
        UsedActionToken.objects.create(jti="6f1c1e8a-3b0e-4c55-9a77-2a3c8f0b9d10")
    top_up_series_reminders(NOW + timedelta(days=9))
    assert list(ScheduledReminder.objects.all()) == [pending]
    assert not ScheduledReminder.objects.filter(pk=old.pk).exists()
    assert not UsedActionToken.objects.exists()


@pytest.mark.django_db
def test_worker_tops_up_at_most_every_12_hours(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "librete.contrib.reminders.management.commands.send_reminders.top_up_series_reminders",
        lambda now: calls.append(now) or 0,
    )
    assert top_up_if_due(NOW) == 0
    assert top_up_if_due(NOW + timedelta(hours=11)) is None
    assert top_up_if_due(NOW + timedelta(hours=12)) == 0
    assert calls == [NOW, NOW + timedelta(hours=12)]
    assert WorkerRun.objects.get(name=TOP_UP).last_run_at == NOW + timedelta(hours=12)


@pytest.mark.django_db
def test_time_zone_change_refreshes_series_rows(auth_client, user):
    with time_machine.travel(NOW, tick=False):
        event = daily(user, reminders=[0])
        assert START + timedelta(days=1) in {row[0] for row in occurrence_rows(event)}
        auth_client.patch("/api/users/me/", {"time_zone": "Europe/Sofia"})
    # 09:00 UTC was 12:00 in Sofia (summer time); occurrences stay at 12:00 local.
    starts = {row[0] for row in occurrence_rows(event)}
    assert START + timedelta(days=1) in starts
    winter = datetime(2030, 11, 1, 10, 0, tzinfo=UTC)
    with time_machine.travel(winter - timedelta(days=1), tick=False):
        top_up_series_reminders()
    assert winter in {row[0] for row in occurrence_rows(event)}
