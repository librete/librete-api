import pytest

from librete.contrib.categories.models import Category, DefaultCategory
from librete.contrib.categories.services import create_default_categories
from librete.contrib.events.models import Event
from librete.tests.factories import (
    CategoryFactory,
    EventFactory,
    NoteFactory,
    TaskFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_create_and_read(auth_client, user):
    response = auth_client.post("/api/categories/", {"name": "Sport", "description": "Gym"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sport"
    assert body["events_count"] == 0

    response = auth_client.get(f"/api/categories/{body['id']}/")
    assert response.status_code == 200
    assert response.json()["description"] == "Gym"


@pytest.mark.django_db
def test_counts(auth_client, user):
    category = CategoryFactory(author=user)
    EventFactory.create_batch(2, author=user, category=category)
    NoteFactory.create_batch(3, author=user, category=category)
    TaskFactory(author=user, category=category)

    body = auth_client.get(f"/api/categories/{category.id}/").json()
    assert (body["events_count"], body["notes_count"], body["tasks_count"]) == (2, 3, 1)


@pytest.mark.django_db
def test_update(auth_client, user):
    category = CategoryFactory(author=user)
    response = auth_client.patch(f"/api/categories/{category.id}/", {"name": "Renamed"})
    assert response.status_code == 200
    category.refresh_from_db()
    assert category.name == "Renamed"


@pytest.mark.django_db
def test_name_is_required(auth_client):
    response = auth_client.post("/api/categories/", {"description": "no name"})
    assert response.status_code == 400
    assert "name" in response.json()


@pytest.mark.django_db
def test_delete_cascades_to_items(auth_client, user):
    category = CategoryFactory(author=user)
    EventFactory(author=user, category=category)
    assert auth_client.delete(f"/api/categories/{category.id}/").status_code == 204
    assert not Category.objects.filter(pk=category.pk).exists()
    assert not Event.objects.exists()


@pytest.mark.django_db
def test_search_and_ordering(auth_client, user):
    CategoryFactory(author=user, name="Banana")
    CategoryFactory(author=user, name="Apple")
    names = [
        c["name"] for c in auth_client.get("/api/categories/?ordering=name").json()["results"]
    ]
    assert names == ["Apple", "Banana"]
    results = auth_client.get("/api/categories/?search=ban").json()["results"]
    assert [c["name"] for c in results] == ["Banana"]


@pytest.mark.django_db
def test_default_categories_use_user_language_with_fallback():
    assert DefaultCategory.objects.count() == 3  # seeded by a data migration
    only_english = DefaultCategory.objects.create()
    only_english.set_current_language("en")
    only_english.name = "Hobbies"
    only_english.save()

    user = UserFactory(language="bg")
    names = {c.name for c in create_default_categories(user)}
    assert names == {"Лични", "Работа", "Дом", "Hobbies"}


@pytest.mark.django_db
def test_color_is_stored_in_lower_case_and_can_be_cleared(auth_client, user):
    response = auth_client.post("/api/categories/", {"name": "Work", "color": "#1E88E5"})
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["color"] == "#1e88e5"
    assert Category.objects.get(pk=body["id"]).color == "#1e88e5"

    url = f"/api/categories/{body['id']}/"
    assert auth_client.patch(url, {"color": "#ABCDEF"}).json()["color"] == "#abcdef"
    assert auth_client.patch(url, {"color": None}).json()["color"] is None
    assert auth_client.post("/api/categories/", {"name": "Plain"}).json()["color"] is None


@pytest.mark.django_db
@pytest.mark.parametrize("color", ["red", "#fff", "1e88e5", "#1e88e5ff", "#1e88eg", ""])
def test_invalid_colors_are_rejected(auth_client, user, color):
    response = auth_client.post("/api/categories/", {"name": "Work", "color": color})
    assert response.status_code == 400
    assert "color" in response.json()
