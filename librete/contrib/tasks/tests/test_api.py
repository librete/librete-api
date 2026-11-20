import pytest

from librete.contrib.tasks.models import Task
from librete.tests.factories import CategoryFactory, TaskFactory


@pytest.fixture
def category(user):
    return CategoryFactory(author=user)


@pytest.mark.django_db
def test_create_with_defaults(auth_client, category):
    response = auth_client.post("/api/tasks/", {"name": "Buy milk", "category": category.id})
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "active"
    assert body["priority"] == ""
    assert body["start_date"] is None
    assert body["parent"] is None


@pytest.mark.django_db
def test_invalid_choices(auth_client, category):
    response = auth_client.post(
        "/api/tasks/",
        {"name": "x", "category": category.id, "priority": "urgent", "status": "done"},
    )
    assert response.status_code == 400
    assert set(response.json()) == {"priority", "status"}


@pytest.mark.django_db
def test_finish_task(auth_client, user, category):
    task = TaskFactory(author=user, category=category)
    response = auth_client.patch(f"/api/tasks/{task.id}/", {"status": "finished"})
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.FINISHED


@pytest.mark.django_db
def test_end_before_start_is_rejected(auth_client, category):
    response = auth_client.post(
        "/api/tasks/",
        {
            "name": "x",
            "category": category.id,
            "start_date": "2030-01-02T00:00:00Z",
            "end_date": "2030-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_subtasks(auth_client, user, category):
    parent = TaskFactory(author=user, category=category)
    response = auth_client.post(
        "/api/tasks/", {"name": "child", "category": category.id, "parent": parent.id}
    )
    assert response.status_code == 201
    child_id = response.json()["id"]

    results = auth_client.get(f"/api/tasks/?parent={parent.id}").json()["results"]
    assert [t["id"] for t in results] == [child_id]
    results = auth_client.get("/api/tasks/?parent__isnull=true").json()["results"]
    assert [t["id"] for t in results] == [parent.id]


@pytest.mark.django_db
def test_parent_cycles_are_rejected(auth_client, user, category):
    root = TaskFactory(author=user, category=category)
    child = TaskFactory(author=user, category=category, parent=root)

    response = auth_client.patch(f"/api/tasks/{root.id}/", {"parent": root.id})
    assert response.status_code == 400
    response = auth_client.patch(f"/api/tasks/{root.id}/", {"parent": child.id})
    assert response.status_code == 400


@pytest.mark.django_db
def test_parent_must_belong_to_user(auth_client, other_user, category):
    foreign = TaskFactory(author=other_user)
    response = auth_client.post(
        "/api/tasks/", {"name": "x", "category": category.id, "parent": foreign.id}
    )
    assert response.status_code == 400
    assert "parent" in response.json()


@pytest.mark.django_db
def test_filter_by_status_and_priority(auth_client, user, category):
    TaskFactory(author=user, category=category, name="a", status="finished", priority="low")
    TaskFactory(author=user, category=category, name="b", status="active", priority="low")
    TaskFactory(author=user, category=category, name="c", status="active", priority="high")
    results = auth_client.get("/api/tasks/?status=active&priority=low").json()["results"]
    assert [t["name"] for t in results] == ["b"]
