import pytest

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
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_reminders_are_deduplicated_and_sorted_descending(auth_client, category):
    response = auth_client.post("/api/events/", payload(category, reminders=[15, 60, 0, 15]))
    assert response.status_code == 201, response.json()
    assert response.json()["reminders"] == [60, 15, 0]


@pytest.mark.django_db
def test_five_distinct_reminders_after_deduplication_are_allowed(auth_client, category):
    reminders = [1, 2, 3, 4, 5, 5, 1]
    response = auth_client.post("/api/events/", payload(category, reminders=reminders))
    assert response.status_code == 201, response.json()
    assert response.json()["reminders"] == [5, 4, 3, 2, 1]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "reminders",
    [
        [-1],
        [40321],
        [1, 2, 3, 4, 5, 6],
        [1.5],
        ["soon"],
        [None],
        15,
        {"minutes": 15},
    ],
)
def test_invalid_reminders_are_rejected(auth_client, category, reminders):
    response = auth_client.post("/api/events/", payload(category, reminders=reminders))
    assert response.status_code == 400
    assert "reminders" in response.json()


@pytest.mark.django_db
def test_boundaries_are_accepted(auth_client, category):
    response = auth_client.post("/api/events/", payload(category, reminders=[0, 40320]))
    assert response.status_code == 201, response.json()
    assert response.json()["reminders"] == [40320, 0]


@pytest.mark.django_db
def test_default_comes_from_the_author_on_create(auth_client, user, category):
    user.default_reminders = [1440, 30]
    user.save()
    response = auth_client.post("/api/events/", payload(category))
    assert response.status_code == 201, response.json()
    assert response.json()["reminders"] == [1440, 30]


@pytest.mark.django_db
def test_new_users_default_to_fifteen_minutes(auth_client, category):
    response = auth_client.post("/api/events/", payload(category))
    assert response.json()["reminders"] == [15]


@pytest.mark.django_db
def test_empty_list_means_no_reminders(auth_client, category):
    response = auth_client.post("/api/events/", payload(category, reminders=[]))
    assert response.status_code == 201, response.json()
    assert response.json()["reminders"] == []


@pytest.mark.django_db
def test_update_keeps_reminders_unless_sent(auth_client, user, category):
    event = EventFactory(author=user, category=category, reminders=[60])
    url = f"/api/events/{event.id}/"

    assert auth_client.patch(url, {"name": "Renamed"}).json()["reminders"] == [60]
    put = payload(category, name="Put")
    assert auth_client.put(url, put).json()["reminders"] == [60]
    assert auth_client.patch(url, {"reminders": [5, 10]}).json()["reminders"] == [10, 5]
    assert auth_client.patch(url, {"reminders": []}).json()["reminders"] == []


@pytest.mark.django_db
def test_validation_errors_are_translated(auth_client, category):
    response = auth_client.post(
        "/api/events/",
        payload(category, reminders=[1, 2, 3, 4, 5, 6]),
        HTTP_ACCEPT_LANGUAGE="bg",
    )
    assert response.json()["reminders"] == ["Позволени са най-много 5 напомняния."]
