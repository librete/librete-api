import pytest

from librete.tests.factories import CategoryFactory, NoteFactory


@pytest.mark.django_db
def test_crud(auth_client, user):
    category = CategoryFactory(author=user)
    response = auth_client.post(
        "/api/notes/", {"name": "Idea", "category": category.id, "text": "x" * 5000}
    )
    assert response.status_code == 201, response.json()
    note_id = response.json()["id"]
    assert len(response.json()["text"]) == 5000  # notes are no longer limited to 1000 chars

    response = auth_client.put(
        f"/api/notes/{note_id}/", {"name": "Idea 2", "category": category.id, "text": "t"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Idea 2"

    assert auth_client.delete(f"/api/notes/{note_id}/").status_code == 204
    assert auth_client.get(f"/api/notes/{note_id}/").status_code == 404


@pytest.mark.django_db
def test_text_is_required(auth_client, user):
    category = CategoryFactory(author=user)
    response = auth_client.post("/api/notes/", {"name": "Idea", "category": category.id})
    assert response.status_code == 400
    assert "text" in response.json()


@pytest.mark.django_db
def test_search(auth_client, user):
    NoteFactory(author=user, name="Shopping", text="milk, eggs")
    NoteFactory(author=user, name="Books", text="Dune")
    results = auth_client.get("/api/notes/?search=eggs").json()["results"]
    assert [n["name"] for n in results] == ["Shopping"]


@pytest.mark.django_db
def test_ordering_newest_first(auth_client, user):
    NoteFactory(author=user, name="first")
    NoteFactory(author=user, name="second")
    results = auth_client.get("/api/notes/?ordering=-created_at").json()["results"]
    assert [n["name"] for n in results] == ["second", "first"]
