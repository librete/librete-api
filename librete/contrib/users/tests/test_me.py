import pytest

from librete.contrib.categories.models import Category
from librete.contrib.events.models import Event
from librete.contrib.users.models import User
from librete.tests.factories import PASSWORD, EventFactory


@pytest.mark.django_db
def test_get_me(auth_client, user):
    response = auth_client.get("/api/users/me/")
    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "email": user.email,
        "first_name": "John",
        "last_name": "Doe",
        "language": "en",
        "time_zone": "UTC",
        "default_reminders": [15],
        "default_task_reminders": [],
        "date_joined": response.json()["date_joined"],
    }


@pytest.mark.django_db
def test_update_me_ignores_read_only_fields(auth_client, user):
    response = auth_client.patch(
        "/api/users/me/",
        {"first_name": "Richard", "language": "bg", "email": "hacker@example.com", "id": 999},
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert (user.first_name, user.language) == ("Richard", "bg")
    assert user.email != "hacker@example.com"


@pytest.mark.django_db
def test_update_me_rejects_unknown_language(auth_client):
    assert auth_client.patch("/api/users/me/", {"language": "xx"}).status_code == 400


@pytest.mark.django_db
def test_update_time_zone_and_default_reminders(auth_client, user):
    response = auth_client.patch(
        "/api/users/me/", {"time_zone": "Europe/Sofia", "default_reminders": [15, 1440, 15]}
    )
    assert response.status_code == 200, response.json()
    assert response.json()["time_zone"] == "Europe/Sofia"
    assert response.json()["default_reminders"] == [1440, 15]
    user.refresh_from_db()
    assert (user.time_zone, user.default_reminders) == ("Europe/Sofia", [1440, 15])

    response = auth_client.patch("/api/users/me/", {"default_reminders": []})
    assert response.json()["default_reminders"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("time_zone", ["Mars/Olympus", "", "europe/sofia", "x" * 65])
def test_update_me_rejects_invalid_time_zone(auth_client, time_zone):
    response = auth_client.patch("/api/users/me/", {"time_zone": time_zone})
    assert response.status_code == 400
    assert "time_zone" in response.json()


@pytest.mark.django_db
@pytest.mark.parametrize("reminders", [[-1], [40321], [1, 2, 3, 4, 5, 6], "15", [None]])
def test_update_me_rejects_invalid_default_reminders(auth_client, reminders):
    response = auth_client.patch("/api/users/me/", {"default_reminders": reminders})
    assert response.status_code == 400
    assert "default_reminders" in response.json()


@pytest.mark.django_db
def test_delete_account_requires_password(auth_client, user):
    EventFactory(author=user)

    response = auth_client.post("/api/users/me/delete/", {"password": "wrong"})
    assert response.status_code == 400
    assert User.objects.filter(pk=user.pk).exists()

    response = auth_client.post("/api/users/me/delete/", {"password": PASSWORD})
    assert response.status_code == 204
    assert not User.objects.filter(pk=user.pk).exists()
    assert not Event.objects.exists()
    assert not Category.objects.exists()


@pytest.mark.django_db
def test_there_is_no_user_list_or_detail(auth_client, other_user):
    assert auth_client.get("/api/users/").status_code == 404
    assert auth_client.get(f"/api/users/{other_user.pk}/").status_code == 404
    assert auth_client.delete(f"/api/users/{other_user.pk}/").status_code == 404
    assert User.objects.filter(pk=other_user.pk).exists()


@pytest.mark.django_db
def test_reverse_accessors(user):
    EventFactory(author=user)
    assert user.categories.count() == 1
    assert user.events.count() == 1
    assert user.notes.count() == 0
    assert user.tasks.count() == 0
