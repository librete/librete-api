"""Creates carrying a `client_id` are idempotent, so the app can safely retry a POST."""

import uuid

import pytest
from django.apps import apps

from librete.tests.factories import CategoryFactory
from librete.utils.viewsets import OwnedModelViewSet

MODELS = {"categories": "Category", "events": "Event", "notes": "Note", "tasks": "Task"}


def model_for(resource):
    return apps.get_model(resource, MODELS[resource])


def payload_for(resource, user, **extra):
    category = CategoryFactory(author=user)
    return {
        "name": "Item",
        "category": category.id,
        "text": "text",
        "start_date": "2030-01-01T10:00:00Z",
        "end_date": "2030-01-01T11:00:00Z",
        **extra,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("resource", MODELS)
def test_repeated_post_returns_the_existing_item(auth_client, user, resource):
    client_id = str(uuid.uuid4())
    payload = payload_for(resource, user, client_id=client_id)

    first = auth_client.post(f"/api/{resource}/", payload)
    assert first.status_code == 201, first.json()
    assert first.json()["client_id"] == client_id

    # The retry is answered from the existing row; its payload is ignored, even if invalid.
    second = auth_client.post(f"/api/{resource}/", {"client_id": client_id, "name": ""})
    assert second.status_code == 200
    assert second.json() == first.json()
    assert model_for(resource).objects.filter(client_id=client_id).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("resource", MODELS)
def test_client_id_is_optional(auth_client, user, resource):
    response = auth_client.post(f"/api/{resource}/", payload_for(resource, user))
    assert response.status_code == 201
    assert response.json()["client_id"] is None
    response = auth_client.post(f"/api/{resource}/", payload_for(resource, user, client_id=None))
    assert response.status_code == 201


@pytest.mark.django_db
def test_invalid_client_id_is_a_validation_error(auth_client, user):
    response = auth_client.post("/api/notes/", payload_for("notes", user, client_id="nope"))
    assert response.status_code == 400
    assert "client_id" in response.json()


@pytest.mark.django_db
@pytest.mark.parametrize("resource", MODELS)
def test_other_users_may_reuse_a_client_id(user, other_user, client_for, resource):
    client_id = str(uuid.uuid4())
    mine = client_for(user).post(
        f"/api/{resource}/", payload_for(resource, user, client_id=client_id)
    )
    theirs = client_for(other_user).post(
        f"/api/{resource}/", payload_for(resource, other_user, client_id=client_id)
    )
    assert mine.status_code == theirs.status_code == 201
    assert mine.json()["id"] != theirs.json()["id"]


@pytest.mark.django_db
@pytest.mark.parametrize("resource", MODELS)
def test_concurrent_create_returns_the_winner(auth_client, user, resource, monkeypatch):
    """The early lookup misses (the other request has not committed yet); the insert then
    hits the unique constraint and the winner's row is returned."""
    client_id = str(uuid.uuid4())
    winner = auth_client.post(
        f"/api/{resource}/", payload_for(resource, user, client_id=client_id)
    )

    original = OwnedModelViewSet._existing_for_client_id
    calls = []

    def miss_first_time(self):
        calls.append(1)
        return None if len(calls) == 1 else original(self)

    monkeypatch.setattr(OwnedModelViewSet, "_existing_for_client_id", miss_first_time)
    response = auth_client.post(
        f"/api/{resource}/", payload_for(resource, user, client_id=client_id)
    )
    assert response.status_code == 200
    assert response.json()["id"] == winner.json()["id"]
    assert len(calls) == 2
    assert model_for(resource).objects.filter(author=user, client_id=client_id).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("resource", MODELS)
def test_client_id_is_ignored_on_update(auth_client, user, resource):
    client_id = str(uuid.uuid4())
    payload = payload_for(resource, user, client_id=client_id)
    item_id = auth_client.post(f"/api/{resource}/", payload).json()["id"]
    url = f"/api/{resource}/{item_id}/"

    response = auth_client.patch(url, {"client_id": str(uuid.uuid4())})
    assert response.status_code == 200
    assert response.json()["client_id"] == client_id

    response = auth_client.put(url, {**payload, "client_id": None})
    assert response.status_code == 200
    assert response.json()["client_id"] == client_id
