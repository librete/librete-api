import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from librete.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttling and allauth rate limits live in the cache; isolate tests from each other."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def other_user(db):
    return UserFactory()


@pytest.fixture
def client_for():
    def make(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    return make


@pytest.fixture
def auth_client(user, client_for):
    return client_for(user)
