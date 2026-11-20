import pytest

from librete.tests.factories import NoteFactory


@pytest.mark.django_db
def test_pagination_and_page_size(auth_client, user):
    NoteFactory.create_batch(30, author=user)

    response = auth_client.get("/api/notes/")
    body = response.json()
    assert body["count"] == 30
    assert len(body["results"]) == 25
    assert body["next"] is not None

    response = auth_client.get(body["next"])
    assert len(response.json()["results"]) == 5

    response = auth_client.get("/api/notes/?page_size=100")
    assert len(response.json()["results"]) == 30
    assert response.json()["next"] is None


@pytest.mark.django_db
def test_page_size_is_capped(auth_client, user):
    NoteFactory.create_batch(3, author=user)
    response = auth_client.get("/api/notes/?page_size=100000")
    assert response.status_code == 200
