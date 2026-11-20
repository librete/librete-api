"""The app sends Accept-Language; emails and errors follow the user's language."""

import pytest
from django.core import mail

from librete.tests.factories import PASSWORD, CategoryFactory


@pytest.mark.django_db
def test_emails_in_bulgarian(api_client):
    api_client.post(
        "/_allauth/app/v1/auth/signup",
        {"email": "ivan@example.com", "password": PASSWORD},
        HTTP_ACCEPT_LANGUAGE="bg",
    )
    body = mail.outbox[-1].body
    assert "Здравейте от Либрете!" in body
    assert "Въведете го в приложението Либрете." in body


@pytest.mark.django_db
def test_validation_errors_in_bulgarian(auth_client, user):
    category = CategoryFactory(author=user)
    response = auth_client.post(
        "/api/events/",
        {
            "name": "x",
            "category": category.id,
            "start_date": "2030-01-02T00:00:00Z",
            "end_date": "2030-01-01T00:00:00Z",
        },
        HTTP_ACCEPT_LANGUAGE="bg",
    )
    assert response.json()["end_date"] == ["Крайната дата не може да бъде преди началната."]

    response = auth_client.post("/api/notes/", {}, HTTP_ACCEPT_LANGUAGE="bg")
    assert response.json()["name"] == ["Това поле е задължително."]  # Django/DRF catalogue


@pytest.mark.django_db
def test_english_is_the_default(auth_client):
    response = auth_client.post("/api/notes/", {})
    assert response.json()["name"] == ["This field is required."]
