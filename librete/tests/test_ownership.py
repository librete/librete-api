"""Every user-owned resource must be invisible and immutable to other users."""

import pytest

from librete.tests.factories import CategoryFactory, EventFactory, NoteFactory, TaskFactory

RESOURCES = [
    ("categories", CategoryFactory, {"name": "Hijacked"}),
    ("events", EventFactory, {"name": "Hijacked"}),
    ("notes", NoteFactory, {"name": "Hijacked"}),
    ("tasks", TaskFactory, {"name": "Hijacked"}),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("resource", "factory", "payload"), RESOURCES)
def test_other_users_objects_are_hidden(auth_client, user, other_user, resource, factory, payload):
    mine = factory(author=user)
    theirs = factory(author=other_user)

    response = auth_client.get(f"/api/{resource}/")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["results"]]
    assert mine.id in ids
    assert theirs.id not in ids

    url = f"/api/{resource}/{theirs.id}/"
    assert auth_client.get(url).status_code == 404
    assert auth_client.patch(url, payload).status_code == 404
    assert auth_client.delete(url).status_code == 404
    theirs.refresh_from_db()
    assert theirs.name != "Hijacked"


@pytest.mark.django_db
@pytest.mark.parametrize("resource", ["events", "notes", "tasks"])
def test_cannot_use_another_users_category(auth_client, user, other_user, resource):
    foreign_category = CategoryFactory(author=other_user)
    payload = {
        "name": "Item",
        "category": foreign_category.id,
        "text": "text",
        "start_date": "2030-01-01T10:00:00Z",
        "end_date": "2030-01-01T11:00:00Z",
    }
    response = auth_client.post(f"/api/{resource}/", payload)
    assert response.status_code == 400
    assert "category" in response.json()


@pytest.mark.django_db
@pytest.mark.parametrize("resource", ["categories", "events", "notes", "tasks"])
def test_author_cannot_be_set_by_client(auth_client, user, other_user, resource):
    category = CategoryFactory(author=user)
    payload = {
        "name": "Item",
        "author": other_user.id,
        "category": category.id,
        "text": "text",
        "start_date": "2030-01-01T10:00:00Z",
        "end_date": "2030-01-01T11:00:00Z",
    }
    response = auth_client.post(f"/api/{resource}/", payload)
    assert response.status_code == 201, response.json()
    assert "author" not in response.json()
    model = {"categories": "Category", "events": "Event", "notes": "Note", "tasks": "Task"}
    from django.apps import apps

    obj = apps.get_model(resource, model[resource]).objects.get(pk=response.json()["id"])
    assert obj.author == user
