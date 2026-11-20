from datetime import UTC, datetime, timedelta

import pytest

from librete.contrib.reminders.models import ScheduledReminder
from librete.tests.factories import CategoryFactory, EventFactory

START = datetime(2030, 5, 1, 18, 0, tzinfo=UTC)


def schedule(event):
    return {
        r.minutes_before: (r.remind_at, r.sent_at)
        for r in ScheduledReminder.objects.filter(event=event)
    }


@pytest.mark.django_db
def test_rows_are_created_with_the_event():
    event = EventFactory(start_date=START, reminders=[60, 15])
    assert schedule(event) == {
        60: (START - timedelta(minutes=60), None),
        15: (START - timedelta(minutes=15), None),
    }


@pytest.mark.django_db
def test_offsets_change_adds_and_removes_rows_and_keeps_unchanged_ones():
    event = EventFactory(start_date=START, reminders=[60, 15])
    sent = START - timedelta(minutes=59)
    ScheduledReminder.objects.filter(event=event, minutes_before=60).update(sent_at=sent)

    event.reminders = [60, 5]
    event.save()

    assert schedule(event) == {
        60: (START - timedelta(minutes=60), sent),  # unchanged, still sent
        5: (START - timedelta(minutes=5), None),
    }


@pytest.mark.django_db
def test_start_date_change_reschedules_and_resets_sent_at():
    event = EventFactory(start_date=START, reminders=[60])
    ScheduledReminder.objects.update(sent_at=START - timedelta(minutes=60))

    new_start = START + timedelta(days=1)
    event.start_date = new_start
    event.end_date = new_start + timedelta(hours=1)
    event.save()

    assert schedule(event) == {60: (new_start - timedelta(minutes=60), None)}


@pytest.mark.django_db
def test_saving_without_changes_keeps_sent_at():
    event = EventFactory(start_date=START, reminders=[60])
    sent = START - timedelta(minutes=60)
    ScheduledReminder.objects.update(sent_at=sent)

    event.name = "Renamed"
    event.save()
    event.save(update_fields=["name"])

    assert schedule(event) == {60: (START - timedelta(minutes=60), sent)}


@pytest.mark.django_db
def test_empty_reminders_remove_all_rows():
    event = EventFactory(start_date=START, reminders=[60, 15])
    event.reminders = []
    event.save()
    assert schedule(event) == {}


@pytest.mark.django_db
def test_rows_are_deleted_with_the_event():
    event = EventFactory(start_date=START, reminders=[60, 15])
    EventFactory(start_date=START, reminders=[10])
    event.delete()
    assert list(ScheduledReminder.objects.values_list("minutes_before", flat=True)) == [10]


@pytest.mark.django_db
def test_api_create_update_and_delete_keep_rows_in_sync(auth_client, user):
    category = CategoryFactory(author=user)
    response = auth_client.post(
        "/api/events/",
        {
            "name": "Concert",
            "category": category.id,
            "start_date": "2030-05-01T18:00:00Z",
            "end_date": "2030-05-01T21:00:00Z",
            "reminders": [60, 15],
        },
    )
    event_id = response.json()["id"]
    url = f"/api/events/{event_id}/"
    rows = ScheduledReminder.objects.filter(event_id=event_id)
    assert sorted(rows.values_list("minutes_before", "remind_at")) == [
        (15, START - timedelta(minutes=15)),
        (60, START - timedelta(minutes=60)),
    ]

    rows.update(sent_at=START - timedelta(minutes=60))
    auth_client.patch(url, {"start_date": "2030-05-01T17:00:00Z"})
    earlier = START - timedelta(hours=1)
    assert sorted(rows.values_list("minutes_before", "remind_at", "sent_at")) == [
        (15, earlier - timedelta(minutes=15), None),
        (60, earlier - timedelta(minutes=60), None),
    ]

    auth_client.patch(url, {"reminders": [0]})
    assert list(rows.values_list("minutes_before", "remind_at")) == [(0, earlier)]

    assert auth_client.delete(url).status_code == 204
    assert not ScheduledReminder.objects.exists()
