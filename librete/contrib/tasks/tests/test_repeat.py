import uuid
from datetime import UTC, datetime, timedelta

import pytest

from librete.contrib.sync.models import Change
from librete.contrib.tasks.models import Task
from librete.contrib.tasks.services import next_instance_client_id
from librete.tests.factories import CategoryFactory, TaskFactory, UserFactory

DUE = datetime(2030, 5, 1, 15, 0, tzinfo=UTC)
SERIES_ID = uuid.UUID("6f1c1e8a-3b0e-4c55-9a77-2a3c8f0b9d10")


def repeating(author, rule="FREQ=DAILY", **kwargs):
    kwargs.setdefault("end_date", DUE)
    return TaskFactory(author=author, repeat=rule, **kwargs)


def finish(client, task, method="patch"):
    url = f"/api/tasks/{task.id}/"
    if method == "patch":
        response = client.patch(url, {"status": "finished"})
    else:
        data = client.get(url).json()
        data["status"] = "finished"
        response = client.put(url, data)
    assert response.status_code == 200, response.json()
    return response.json()


def instances(task):
    return Task.objects.filter(author=task.author).exclude(pk=task.pk)


def test_client_id_rule_with_a_hard_coded_expectation():
    task = Task(pk=7, client_id=SERIES_ID)
    next_due = datetime(2030, 5, 8, 9, 0, tzinfo=UTC)
    assert next_instance_client_id(task, next_due) == uuid.UUID(
        "63ad4d2a-0cf6-5635-8b7a-dd919f24a01a"
    )
    # Without a client_id the series key is "id:<pk>"; the time is formatted in UTC.
    task = Task(pk=42, client_id=None)
    local = datetime(2030, 5, 2, 18, 0, tzinfo=UTC) + timedelta(hours=-3)
    assert next_instance_client_id(task, local) == uuid.UUID(
        "163dec6c-83e3-5377-8f6f-393f91e47058"
    )
    assert next_instance_client_id(task, local) == uuid.uuid5(
        uuid.NAMESPACE_URL, "librete:task-repeat:id:42:2030-05-02T15:00:00Z"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["patch", "put"])
def test_completing_creates_the_next_instance(auth_client, user, method):
    category = CategoryFactory(author=user)
    parent = TaskFactory(author=user, category=category)
    task = repeating(
        user,
        rule="FREQ=WEEKLY",
        category=category,
        parent=parent,
        name="Water plants",
        description="Balcony",
        priority=Task.Priority.LOW,
        start_date=DUE - timedelta(hours=2),
        client_id=SERIES_ID,
    )
    TaskFactory(author=user, category=category, parent=task, name="Subtask")

    finish(auth_client, task, method)

    nxt = Task.objects.get(
        author=user, client_id=next_instance_client_id(task, DUE + timedelta(7))
    )
    assert (nxt.name, nxt.category, nxt.parent, nxt.description, nxt.priority) == (
        "Water plants",
        category,
        parent,
        "Balcony",
        Task.Priority.LOW,
    )
    assert nxt.status == Task.Status.ACTIVE
    assert nxt.repeat == "FREQ=WEEKLY"
    assert nxt.end_date == DUE + timedelta(days=7)
    assert nxt.start_date == DUE + timedelta(days=7, hours=-2)
    assert nxt.version == 1
    assert not nxt.subtasks.exists()
    task.refresh_from_db()
    assert task.status == Task.Status.FINISHED


@pytest.mark.django_db
def test_next_instance_is_in_the_change_log_and_the_api(auth_client, user):
    task = repeating(user)
    cursor = auth_client.get("/api/sync/").json()["cursor"]
    finish(auth_client, task)
    nxt = instances(task).get()
    changes = auth_client.get("/api/sync/", {"since": cursor}).json()["changes"]
    assert [(c["type"], c["id"], c["op"]) for c in changes] == [
        ("tasks", task.id, "upsert"),
        ("tasks", nxt.id, "upsert"),
    ]
    assert changes[1]["data"]["client_id"] == str(nxt.client_id)
    assert changes[1]["data"]["repeat"] == "FREQ=DAILY"
    assert Change.objects.filter(user=user, type="tasks", object_id=nxt.id).exists()


@pytest.mark.django_db
def test_start_date_is_the_due_date_without_an_end_date(user):
    task = repeating(user, rule="FREQ=MONTHLY", end_date=None, start_date=DUE)
    task.status = Task.Status.FINISHED
    task.save()
    nxt = instances(task).get()
    assert (nxt.start_date, nxt.end_date) == (datetime(2030, 6, 1, 15, tzinfo=UTC), None)


@pytest.mark.django_db
def test_next_date_follows_the_rule_in_the_users_time_zone():
    user = UserFactory(time_zone="Europe/Sofia")
    # Friday 29 March 2030, 18:00 in Sofia (UTC+2); the next weekday is Monday 1 April,
    # 18:00 summer time (UTC+3).
    task = repeating(
        user,
        rule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
        end_date=datetime(2030, 3, 29, 16, tzinfo=UTC),
    )
    task.status = Task.Status.FINISHED
    task.save()
    assert instances(task).get().end_date == datetime(2030, 4, 1, 15, tzinfo=UTC)


@pytest.mark.django_db
def test_month_end_and_leap_day(user):
    monthly = repeating(
        user, rule="FREQ=MONTHLY;BYMONTHDAY=-1", end_date=datetime(2032, 1, 31, 9, tzinfo=UTC)
    )
    yearly = repeating(user, rule="FREQ=YEARLY", end_date=datetime(2028, 2, 29, 9, tzinfo=UTC))
    for task in (monthly, yearly):
        task.status = Task.Status.FINISHED
        task.save()
    created = sorted(
        Task.objects.exclude(pk__in=[monthly.pk, yearly.pk]).values_list("end_date", flat=True)
    )
    assert created == [datetime(2032, 2, 29, 9, tzinfo=UTC), datetime(2032, 2, 29, 9, tzinfo=UTC)]


@pytest.mark.django_db
def test_nothing_is_created_when_the_client_already_created_it(auth_client, user):
    task = repeating(user, client_id=SERIES_ID)
    client_id = next_instance_client_id(task, DUE + timedelta(days=1))
    offline = auth_client.post(
        "/api/tasks/",
        {
            "client_id": str(client_id),
            "name": task.name,
            "category": task.category_id,
            "end_date": "2030-05-02T15:00:00Z",
            "repeat": "FREQ=DAILY",
        },
    )
    assert offline.status_code == 201
    finish(auth_client, task)
    assert instances(task).count() == 1
    assert instances(task).get().pk == offline.json()["id"]


@pytest.mark.django_db
def test_completing_again_is_idempotent(auth_client, user):
    task = repeating(user)
    finish(auth_client, task)
    auth_client.patch(f"/api/tasks/{task.id}/", {"status": "active"})
    assert instances(task).count() == 1  # un-finishing keeps it
    finish(auth_client, task)
    finish(auth_client, task)  # already finished: not a completion
    assert instances(task).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("rule", ["FREQ=DAILY;COUNT=1", "FREQ=DAILY;UNTIL=20300501T150000Z"])
def test_no_instance_after_the_rule_ended(user, rule):
    task = repeating(user, rule=rule)
    task.status = Task.Status.FINISHED
    task.save()
    assert not instances(task).exists()


@pytest.mark.django_db
def test_count_runs_out_across_instances(user):
    task = repeating(user, rule="FREQ=DAILY;COUNT=3")
    chain = [task]
    while True:
        current = chain[-1]
        current.status = Task.Status.FINISHED
        current.save()
        following = Task.objects.filter(author=user, status=Task.Status.ACTIVE).first()
        if following is None:
            break
        chain.append(following)
    assert [t.repeat for t in chain] == [
        "FREQ=DAILY;COUNT=3",
        "FREQ=DAILY;COUNT=2",
        "FREQ=DAILY;COUNT=1",
    ]
    assert [t.end_date for t in chain] == [DUE + timedelta(days=n) for n in range(3)]


@pytest.mark.django_db
def test_other_saves_and_plain_tasks_create_nothing(user):
    task = repeating(user)
    task.name = "Renamed"
    task.save()
    task.status = Task.Status.FINISHED
    task.save(update_fields=["name"])  # status not saved
    plain = TaskFactory(author=user, end_date=DUE)
    plain.status = Task.Status.FINISHED
    plain.save()
    finished = repeating(user, status=Task.Status.FINISHED)
    finished.save()
    assert Task.objects.filter(author=user).count() == 3


@pytest.mark.django_db
def test_repeat_validation(auth_client, user):
    category = CategoryFactory(author=user)

    def post(**fields):
        return auth_client.post("/api/tasks/", {"name": "T", "category": category.id, **fields})

    response = post(repeat="FREQ=DAILY")
    assert response.status_code == 400
    assert "repeat" in response.json()
    assert "repeat" in post(repeat="FREQ=SECONDLY", end_date="2030-05-01T15:00:00Z").json()
    response = post(repeat=" freq=daily ", start_date="2030-05-01T15:00:00Z")
    assert response.status_code == 201
    assert response.json()["repeat"] == "FREQ=DAILY"
    url = f"/api/tasks/{response.json()['id']}/"
    response = auth_client.patch(url, {"start_date": None})
    assert response.status_code == 400
    assert "repeat" in response.json()
    assert post(repeat=None).json()["repeat"] is None
