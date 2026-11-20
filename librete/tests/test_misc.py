import pytest


@pytest.mark.django_db
def test_health(api_client):
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_health_check_from_inside_the_container(api_client, settings):
    # Production only allows the public domain plus the container-local names.
    assert "127.0.0.1" in settings.ALLOWED_HOSTS
    response = api_client.get("/api/health/", HTTP_HOST="127.0.0.1:8000")
    assert response.status_code == 200


@pytest.mark.django_db
def test_openapi_schema(api_client):
    response = api_client.get("/api/schema/?format=json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/events/",
        "/api/tasks/{id}/",
        "/api/users/me/",
        "/api/stats/",
        "/api/push/vapid-key/",
        "/api/push/subscriptions/",
        "/api/push/subscriptions/{id}/",
    ):
        assert path in paths


@pytest.mark.django_db
def test_cors_preflight_allows_app_origins(api_client):
    response = api_client.options(
        "/api/events/",
        HTTP_ORIGIN="capacitor://localhost",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-session-token",
    )
    assert response["access-control-allow-origin"] == "capacitor://localhost"
    assert "x-session-token" in response["access-control-allow-headers"]


@pytest.mark.django_db
def test_cors_rejects_unknown_origin(api_client):
    response = api_client.options(
        "/api/events/",
        HTTP_ORIGIN="https://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )
    assert "access-control-allow-origin" not in response


@pytest.mark.django_db
def test_no_missing_migrations():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out)
