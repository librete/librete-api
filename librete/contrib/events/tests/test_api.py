import pytest

from librete.contrib.events.models import Event
from librete.tests.factories import CategoryFactory, EventFactory


@pytest.fixture
def category(user):
    return CategoryFactory(author=user)


def payload(category, **overrides):
    data = {
        "name": "Concert",
        "category": category.id,
        "start_date": "2030-05-01T18:00:00Z",
        "end_date": "2030-05-01T21:00:00Z",
        "location": "NDK",
        "description": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_create(auth_client, user, category):
    response = auth_client.post("/api/events/", payload(category))
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["category"] == category.id
    assert body["start_date"] == "2030-05-01T18:00:00Z"
    assert Event.objects.get(pk=body["id"]).author == user


@pytest.mark.django_db
def test_location_is_optional(auth_client, category):
    response = auth_client.post("/api/events/", payload(category, location=""))
    assert response.status_code == 201


@pytest.mark.django_db
def test_end_before_start_is_rejected(auth_client, category):
    data = payload(category, end_date="2030-05-01T17:00:00Z")
    response = auth_client.post("/api/events/", data)
    assert response.status_code == 400
    assert "end_date" in response.json()


@pytest.mark.django_db
def test_partial_update_validates_dates_against_stored_values(auth_client, user, category):
    event = EventFactory(author=user, category=category)
    earlier = (event.start_date.replace(year=event.start_date.year - 1)).isoformat()
    response = auth_client.patch(f"/api/events/{event.id}/", {"end_date": earlier})
    assert response.status_code == 400


@pytest.mark.django_db
def test_filters(auth_client, user, category):
    other_category = CategoryFactory(author=user)
    EventFactory(author=user, category=category, name="A")
    EventFactory(author=user, category=other_category, name="B")

    results = auth_client.get(f"/api/events/?category={category.id}").json()["results"]
    assert [e["name"] for e in results] == ["A"]


@pytest.mark.django_db
def test_upcoming_query(auth_client, user, category):
    from datetime import timedelta

    from django.utils import timezone

    now = timezone.now()
    EventFactory(
        author=user,
        category=category,
        name="past",
        start_date=now - timedelta(days=2),
        end_date=now - timedelta(days=1),
    )
    EventFactory(
        author=user,
        category=category,
        name="later",
        start_date=now + timedelta(days=9),
        end_date=now + timedelta(days=10),
    )
    EventFactory(
        author=user,
        category=category,
        name="soon",
        start_date=now + timedelta(days=1),
        end_date=now + timedelta(days=2),
    )

    response = auth_client.get(
        "/api/events/",
        {"start_date__gte": now.isoformat(), "ordering": "start_date", "page_size": 5},
    )
    assert [e["name"] for e in response.json()["results"]] == ["soon", "later"]
