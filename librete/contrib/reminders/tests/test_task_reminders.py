from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, transaction

from librete.contrib.reminders.models import ScheduledReminder
from librete.contrib.tasks.models import Task
from librete.tests.factories import CategoryFactory, EventFactory, TaskFactory, UserFactory

DUE = datetime(2030, 5, 1, 18, 0, tzinfo=UTC)


def schedule(task):
    return {
        r.minutes_before: (r.remind_at, r.sent_at)
        for r in ScheduledReminder.objects.filter(task=task)
    }


@pytest.mark.django_db
def test_defaults_come_from_the_user(client_for):
    user = UserFactory(default_task_reminders=[30, 0])
    category = CategoryFactory(author=user)
    client = client_for(user)
    body = client.post(
        "/api/tasks/",
        {"name": "Pay rent", "category": category.id, "end_date": "2030-05-01T18:00:00Z"},
    ).json()
    assert body["reminders"] == [30, 0]
    explicit = client.post(
        "/api/tasks/",
        {"name": "Call", "category": category.id, "reminders": [5, 60, 5]},
    ).json()
    assert explicit["reminders"] == [60, 5]
    none = client.post(
        "/api/tasks/", {"name": "Read", "category": category.id, "reminders": []}
    ).json()
    assert none["reminders"] == []


@pytest.mark.django_db
def test_user_default_is_empty_and_writable(auth_client, user):
    assert auth_client.get("/api/users/me/").json()["default_task_reminders"] == []
    response = auth_client.patch("/api/users/me/", {"default_task_reminders": [10, 1440]})
    assert response.json()["default_task_reminders"] == [1440, 10]
    assert auth_client.patch("/api/users/me/", {"default_task_reminders": [-1]}).status_code == 400
    user.refresh_from_db()
    assert user.default_task_reminders == [1440, 10]


@pytest.mark.django_db
def test_task_reminders_are_validated(auth_client, user):
    category = CategoryFactory(author=user)
    response = auth_client.post(
        "/api/tasks/", {"name": "T", "category": category.id, "reminders": [1, 2, 3, 4, 5, 6]}
    )
    assert response.status_code == 400
    assert "reminders" in response.json()


@pytest.mark.django_db
def test_rows_are_measured_from_the_due_date_else_the_start(user):
    due = TaskFactory(
        author=user, start_date=DUE - timedelta(days=1), end_date=DUE, reminders=[60]
    )
    started = TaskFactory(author=user, start_date=DUE, reminders=[15, 0])
    assert schedule(due) == {60: (DUE - timedelta(minutes=60), None)}
    assert schedule(started) == {15: (DUE - timedelta(minutes=15), None), 0: (DUE, None)}


@pytest.mark.django_db
def test_no_rows_without_a_date_or_once_finished(user):
    undated = TaskFactory(author=user, reminders=[15])
    assert schedule(undated) == {}

    task = TaskFactory(author=user, end_date=DUE, reminders=[15])
    task.status = Task.Status.FINISHED
    task.save()
    assert schedule(task) == {}
    task.status = Task.Status.ACTIVE
    task.save()
    assert schedule(task) == {15: (DUE - timedelta(minutes=15), None)}


@pytest.mark.django_db
def test_rows_follow_changes_and_deletion(user):
    task = TaskFactory(author=user, end_date=DUE, reminders=[60, 15])
    ScheduledReminder.objects.filter(task=task, minutes_before=60).update(sent_at=DUE)
    task.reminders = [60, 5]
    task.save()
    assert schedule(task) == {
        60: (DUE - timedelta(minutes=60), DUE),
        5: (DUE - timedelta(minutes=5), None),
    }
    task.end_date = DUE + timedelta(days=1)
    task.save()
    assert {m: sent for m, (_, sent) in schedule(task).items()} == {60: None, 5: None}
    task.end_date = None
    task.save()
    assert schedule(task) == {}
    task.end_date = DUE
    task.save()
    task.delete()
    assert not ScheduledReminder.objects.exists()


@pytest.mark.django_db
def test_next_repeat_instance_copies_the_reminders(user):
    task = TaskFactory(author=user, end_date=DUE, reminders=[30], repeat="FREQ=DAILY")
    task.status = Task.Status.FINISHED
    task.save()
    nxt = Task.objects.get(author=user, status=Task.Status.ACTIVE)
    assert nxt.reminders == [30]
    assert schedule(nxt) == {30: (DUE + timedelta(days=1, minutes=-30), None)}


@pytest.mark.django_db
def test_a_reminder_belongs_to_exactly_one_event_or_task(user):
    event = EventFactory(author=user, reminders=[])
    task = TaskFactory(author=user)
    for fields in ({}, {"event": event, "task": task}):
        with pytest.raises(IntegrityError), transaction.atomic():
            ScheduledReminder.objects.create(minutes_before=0, remind_at=DUE, **fields)
    # One-off rows may repeat an offset; derived rows may not.
    for _ in range(2):
        ScheduledReminder.objects.create(task=task, minutes_before=0, remind_at=DUE, one_off=True)
    ScheduledReminder.objects.create(task=task, minutes_before=0, remind_at=DUE)
    with pytest.raises(IntegrityError), transaction.atomic():
        ScheduledReminder.objects.create(task=task, minutes_before=0, remind_at=DUE)


@pytest.mark.django_db
def test_one_off_rows_are_left_alone_by_the_sync(user):
    task = TaskFactory(author=user, end_date=DUE, reminders=[15])
    snooze = ScheduledReminder.objects.create(
        task=task, minutes_before=0, remind_at=DUE + timedelta(hours=1), one_off=True
    )
    task.reminders = []
    task.end_date = None
    task.save()
    assert list(ScheduledReminder.objects.filter(task=task)) == [snooze]


@pytest.mark.django_db
def test_sync_payload_includes_the_task_fields(auth_client, user):
    task = TaskFactory(author=user, end_date=DUE, reminders=[15], repeat="FREQ=WEEKLY")
    [change] = auth_client.get("/api/sync/", {"since": 0, "types": "tasks"}).json()["changes"]
    assert change["data"]["reminders"] == [15]
    assert change["data"]["repeat"] == "FREQ=WEEKLY"
    assert change["data"] == auth_client.get(f"/api/tasks/{task.id}/").json()
