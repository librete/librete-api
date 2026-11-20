from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from django.core import signing

from librete.contrib.reminders.actions import action_url, make_token
from librete.contrib.reminders.models import ScheduledReminder, UsedActionToken
from librete.contrib.sync.models import Change
from librete.contrib.tasks.models import Task
from librete.tests.factories import EventFactory, TaskFactory

NOW = datetime(2030, 5, 1, 12, 0, tzinfo=UTC)


def call(api_client, url):
    return api_client.get(url)


def snoozes():
    return list(
        ScheduledReminder.objects.filter(one_off=True).values_list(
            "event_id", "task_id", "occurrence_start", "remind_at", "minutes_before"
        )
    )


@pytest.mark.django_db
def test_done_finishes_the_task_with_versioning_and_change_log(api_client, user):
    task = TaskFactory(author=user, end_date=NOW, repeat="FREQ=DAILY", reminders=[])
    url = action_url("done", "task", task.id, user.id)

    response = call(api_client, url)

    assert response.status_code == 204
    task.refresh_from_db()
    assert task.status == Task.Status.FINISHED
    assert task.version == 2
    # The repeat instance was created too, and both are in the change log.
    nxt = Task.objects.get(author=user, status=Task.Status.ACTIVE)
    assert nxt.end_date == NOW + timedelta(days=1)
    logged = Change.objects.filter(user=user, type="tasks").values_list("object_id", flat=True)
    assert set(logged) == {task.id, nxt.id}


@pytest.mark.django_db
def test_done_on_a_finished_task_changes_nothing(api_client, user):
    task = TaskFactory(author=user, status=Task.Status.FINISHED)
    assert call(api_client, action_url("done", "task", task.id, user.id)).status_code == 204
    task.refresh_from_db()
    assert task.version == 1


@pytest.mark.django_db
def test_snooze_creates_one_off_reminders(api_client, user):
    task = TaskFactory(author=user, reminders=[])
    event = EventFactory(author=user, reminders=[], recurrence="FREQ=DAILY")
    occurrence = event.start_date + timedelta(days=2)
    with time_machine.travel(NOW, tick=False):
        assert (
            call(
                api_client, action_url("snooze", "task", task.id, user.id, minutes=60)
            ).status_code
            == 204
        )
        url = action_url("snooze", "event", event.id, user.id, minutes=10, occurrence=occurrence)
        assert call(api_client, url).status_code == 204
    assert sorted(snoozes(), key=str) == sorted(
        [
            (None, task.id, None, NOW + timedelta(hours=1), 0),
            (event.id, None, occurrence.replace(microsecond=0), NOW + timedelta(minutes=10), 0),
        ],
        key=str,
    )
    task.refresh_from_db()
    assert task.version == 1  # snoozing doesn't change the item
    # The next save of the item leaves the snoozes alone.
    task.save()
    event.save()
    assert len(snoozes()) == 2


@pytest.mark.django_db
def test_tokens_are_single_use(api_client, user):
    task = TaskFactory(author=user)
    url = action_url("snooze", "task", task.id, user.id, minutes=60)
    assert call(api_client, url).status_code == 204
    response = call(api_client, url)
    assert response.status_code == 410
    assert "detail" in response.json()
    assert len(snoozes()) == 1
    assert UsedActionToken.objects.count() == 1


@pytest.mark.django_db
def test_expired_tokens_change_nothing(api_client, user):
    task = TaskFactory(author=user)
    with time_machine.travel(NOW, tick=False):
        url = action_url("done", "task", task.id, user.id)
    with time_machine.travel(NOW + timedelta(days=7, seconds=1), tick=False):
        assert call(api_client, url).status_code == 410
    with time_machine.travel(NOW + timedelta(days=6, hours=23), tick=False):
        assert call(api_client, url).status_code == 204


@pytest.mark.django_db
def test_tampered_or_malformed_tokens_change_nothing(api_client, user, other_user):
    task = TaskFactory(author=user)
    token = make_token("done", "task", task.id, user.id)
    payload, rest = token.split(":", 1)
    forged = signing.dumps(
        {
            "op": "done",
            "type": "task",
            "id": task.id,
            "occurrence": None,
            "minutes": 0,
            "user": user.id,
            "jti": "6f1c1e8a-3b0e-4c55-9a77-2a3c8f0b9d10",
        },
        salt="another.salt",
    )
    bad_shape = signing.dumps({"op": "done", "type": "event", "id": 1}, salt="librete.actions")
    done_on_event = make_token("done", "event", EventFactory(author=user).id, user.id)
    for bad in (
        token[:-2] + "xx",
        payload[:-3] + "abc:" + rest,
        forged,
        bad_shape,
        done_on_event,
        "x",
    ):
        assert call(api_client, f"/api/actions/{bad}/").status_code == 400, bad
    task.refresh_from_db()
    assert task.status == Task.Status.ACTIVE
    assert not UsedActionToken.objects.exists()


@pytest.mark.django_db
def test_tokens_only_act_on_the_users_own_items(api_client, user, other_user):
    theirs = TaskFactory(author=other_user)
    assert call(api_client, action_url("done", "task", theirs.id, user.id)).status_code == 410
    deleted = TaskFactory(author=user)
    url = action_url("done", "task", deleted.id, user.id)
    deleted.delete()
    assert call(api_client, url).status_code == 410
    theirs.refresh_from_db()
    assert theirs.status == Task.Status.ACTIVE
    assert not UsedActionToken.objects.exists()


@pytest.mark.django_db
def test_no_login_needed_and_a_bad_session_token_is_ignored(api_client, user):
    task = TaskFactory(author=user)
    url = action_url("snooze", "task", task.id, user.id, minutes=60)
    assert api_client.get(url, HTTP_X_SESSION_TOKEN="garbage").status_code == 204


@pytest.mark.django_db
def test_errors_are_translated(api_client):
    response = api_client.get("/api/actions/x/", HTTP_ACCEPT_LANGUAGE="bg")
    assert response.json() == {"detail": "Тази връзка за действие е невалидна."}
