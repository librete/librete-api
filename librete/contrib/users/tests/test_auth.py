"""End-to-end authentication flows through django-allauth's headless "app" API."""

import re

import pytest
from allauth.account.models import EmailAddress
from django.core import mail

from librete.contrib.categories.models import Category
from librete.contrib.users.models import User
from librete.tests.factories import PASSWORD, UserFactory

AUTH = "/_allauth/app/v1"


def _code_from_last_email():
    body = mail.outbox[-1].body
    match = re.search(r"^\s*([A-Z0-9]{4}-[A-Z0-9]{4})\s*$", body, re.MULTILINE)
    assert match, body
    return match.group(1)


@pytest.fixture
def verified_user(db):
    user = UserFactory()
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


@pytest.mark.django_db
def test_signup_verify_email_and_use_api(api_client):
    response = api_client.post(
        f"{AUTH}/auth/signup",
        {
            "email": "jane@example.com",
            "password": PASSWORD,
            "first_name": "Jane",
            "last_name": "Roe",
            "language": "bg",
        },
    )
    # Email verification is mandatory: the flow is pending until the emailed code is entered.
    assert response.status_code == 401
    body = response.json()
    assert {"id": "verify_email", "is_pending": True} in [
        {k: f.get(k) for k in ("id", "is_pending")} for f in body["data"]["flows"]
    ]
    session_token = body["meta"]["session_token"]

    user = User.objects.get(email="jane@example.com")
    assert (user.first_name, user.last_name, user.language) == ("Jane", "Roe", "bg")
    # Default categories are created in the user's language.
    assert set(Category.objects.filter(author=user).values_list("name", flat=True)) == {
        "Лични",
        "Работа",
        "Дом",
    }

    response = api_client.post(
        f"{AUTH}/auth/email/verify",
        {"key": _code_from_last_email()},
        HTTP_X_SESSION_TOKEN=session_token,
    )
    assert response.status_code == 200, response.json()
    token = response.json()["meta"]["session_token"]

    response = api_client.get("/api/users/me/", HTTP_X_SESSION_TOKEN=token)
    assert response.status_code == 200
    assert response.json()["email"] == "jane@example.com"


@pytest.mark.django_db
def test_signup_does_not_reveal_existing_emails(api_client, verified_user):
    # Enumeration prevention: the response looks like a normal pending signup, no second
    # account is created, and the real owner is told by email instead.
    response = api_client.post(
        f"{AUTH}/auth/signup", {"email": verified_user.email, "password": PASSWORD}
    )
    assert response.status_code == 401
    assert User.objects.filter(email=verified_user.email).count() == 1
    assert mail.outbox[-1].to == [verified_user.email]


@pytest.mark.django_db
def test_signup_rejects_weak_password(api_client):
    response = api_client.post(
        f"{AUTH}/auth/signup", {"email": "x@example.com", "password": "123"}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_login_and_logout(api_client, verified_user):
    response = api_client.post(
        f"{AUTH}/auth/login", {"email": verified_user.email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.json()
    token = response.json()["meta"]["session_token"]

    assert api_client.get("/api/users/me/", HTTP_X_SESSION_TOKEN=token).status_code == 200

    response = api_client.delete(f"{AUTH}/auth/session", HTTP_X_SESSION_TOKEN=token)
    assert response.status_code == 401  # allauth answers "no longer authenticated"

    assert api_client.get("/api/users/me/", HTTP_X_SESSION_TOKEN=token).status_code == 401


@pytest.mark.django_db
def test_login_with_wrong_password(api_client, verified_user):
    response = api_client.post(
        f"{AUTH}/auth/login", {"email": verified_user.email, "password": "wrong-password"}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_password_reset_by_code(api_client, verified_user):
    response = api_client.post(f"{AUTH}/auth/password/request", {"email": verified_user.email})
    assert response.status_code == 401  # flow pending: password_reset_by_code
    session_token = response.json()["meta"]["session_token"]

    response = api_client.post(
        f"{AUTH}/auth/password/reset",
        {"key": _code_from_last_email(), "password": "a-brand-new-passphrase"},
        HTTP_X_SESSION_TOKEN=session_token,
    )
    assert response.status_code in (200, 401), response.json()

    verified_user.refresh_from_db()
    assert verified_user.check_password("a-brand-new-passphrase")


@pytest.mark.django_db
def test_api_requires_authentication(api_client):
    for url in ("/api/users/me/", "/api/categories/", "/api/events/", "/api/stats/"):
        assert api_client.get(url).status_code == 401, url
    assert api_client.get("/api/events/", HTTP_X_SESSION_TOKEN="bogus").status_code == 401


@pytest.mark.django_db
def test_emails_are_branded(api_client):
    api_client.post(f"{AUTH}/auth/signup", {"email": "new@example.com", "password": PASSWORD})
    body = mail.outbox[-1].body
    assert "Hello from Librete!" in body
    assert "Librete app" in body
    assert "testserver" not in body
    assert mail.outbox[-1].subject.startswith("[Librete]")
