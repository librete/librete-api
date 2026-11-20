"""Every item has a `version`; `If-Match` turns stale writes into 409 conflicts."""

import pytest

from librete.tests.factories import CategoryFactory, EventFactory, NoteFactory, TaskFactory

FACTORIES = {
    "categories": CategoryFactory,
    "events": EventFactory,
    "notes": NoteFactory,
    "tasks": TaskFactory,
}


@pytest.fixture(params=FACTORIES)
def resource(request):
    return request.param


@pytest.fixture
def item(resource, user):
    return FACTORIES[resource](author=user)


@pytest.fixture
def url(resource, item):
    return f"/api/{resource}/{item.id}/"


def put_payload(resource, item):
    payload = {"name": "Put", "description": "d", "text": "t"}
    if resource != "categories":
        payload["category"] = item.category_id
    if resource == "events":
        payload |= {"start_date": item.start_date, "end_date": item.end_date}
    return payload


@pytest.mark.django_db
def test_version_starts_at_one_and_increments_on_every_update(auth_client, resource, item, url):
    response = auth_client.get(url)
    assert response.json()["version"] == 1
    assert response["ETag"] == '"1"'

    response = auth_client.patch(url, {"name": "Patched"})
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response["ETag"] == '"2"'

    response = auth_client.put(url, put_payload(resource, item))
    assert response.status_code == 200, response.json()
    assert response.json()["version"] == 3

    # Admin and other code paths save the model directly; the version still increases.
    item.refresh_from_db()
    item.name = "Admin"
    item.save()
    assert item.version == 4
    item.save(update_fields=["name"])
    item.refresh_from_db()
    assert item.version == 5
    assert auth_client.get(url).json()["version"] == 5


@pytest.mark.django_db
def test_version_is_read_only(auth_client, url):
    response = auth_client.patch(url, {"version": 42})
    assert response.json()["version"] == 2


@pytest.mark.django_db
def test_stale_save_still_increments_from_the_stored_version(user):
    note = NoteFactory(author=user)
    stale = type(note).objects.get(pk=note.pk)
    note.save()
    stale.save()
    stale.refresh_from_db()
    assert stale.version == 3


@pytest.mark.django_db
def test_create_returns_an_etag(auth_client, user):
    category = CategoryFactory(author=user)
    response = auth_client.post("/api/notes/", {"name": "n", "category": category.id, "text": "t"})
    assert response.status_code == 201
    assert response["ETag"] == '"1"'
    assert "ETag" not in auth_client.get("/api/notes/")


@pytest.mark.django_db
@pytest.mark.parametrize("header", ["1", '"1"', 'W/"1"', " 1 ", "*"])
def test_matching_if_match_applies_the_change(auth_client, url, header):
    response = auth_client.patch(url, {"name": "Patched"}, HTTP_IF_MATCH=header)
    assert response.status_code == 200
    assert response.json()["name"] == "Patched"
    assert response.json()["version"] == 2


@pytest.mark.django_db
def test_matching_if_match_on_put_and_delete(auth_client, resource, item, url):
    response = auth_client.put(url, put_payload(resource, item), HTTP_IF_MATCH='"1"')
    assert response.status_code == 200
    assert auth_client.delete(url, HTTP_IF_MATCH="2").status_code == 204
    assert not type(item).objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_stale_if_match_is_a_conflict(auth_client, resource, item, url):
    auth_client.patch(url, {"name": "Changed elsewhere"})
    expected = auth_client.get(url).json()

    for method, data in (("patch", {"name": "Mine"}), ("put", put_payload(resource, item))):
        response = getattr(auth_client, method)(url, data, HTTP_IF_MATCH="1")
        assert response.status_code == 409
        assert response.json() == {
            "detail": "This item was changed elsewhere.",
            "current": expected,
        }

    response = auth_client.delete(url, HTTP_IF_MATCH='W/"1"')
    assert response.status_code == 409
    assert response.json()["current"] == expected

    item.refresh_from_db()
    assert item.name == "Changed elsewhere"
    assert item.version == 2


@pytest.mark.django_db
def test_conflict_message_is_translated(auth_client, url):
    response = auth_client.patch(url, {"name": "x"}, HTTP_IF_MATCH="7", HTTP_ACCEPT_LANGUAGE="bg")
    assert response.json()["detail"] == "Този елемент е променен другаде."


@pytest.mark.django_db
@pytest.mark.parametrize("header", ["abc", "", '"1', "1, 2", "W/1", "-1", "1.0"])
def test_unparseable_if_match_is_rejected(auth_client, item, url, header):
    response = auth_client.patch(url, {"name": "x"}, HTTP_IF_MATCH=header)
    assert response.status_code == 400
    assert "detail" in response.json()
    assert auth_client.delete(url, HTTP_IF_MATCH=header).status_code == 400
    assert type(item).objects.filter(pk=item.pk, version=1).exists()


@pytest.mark.django_db
def test_if_match_does_not_reveal_other_users_items(auth_client, other_user):
    theirs = NoteFactory(author=other_user)
    response = auth_client.patch(f"/api/notes/{theirs.id}/", {"name": "x"}, HTTP_IF_MATCH="5")
    assert response.status_code == 404


@pytest.mark.django_db
def test_category_conflict_includes_counts(auth_client, user):
    category = CategoryFactory(author=user)
    EventFactory(author=user, category=category)
    url = f"/api/categories/{category.id}/"
    response = auth_client.patch(url, {"name": "x"}, HTTP_IF_MATCH="9")
    assert response.json()["current"]["events_count"] == 1
    response = auth_client.patch(url, {"name": "x"}, HTTP_IF_MATCH="1")
    assert response.json()["events_count"] == 1


@pytest.mark.django_db
def test_cors_allows_if_match_and_exposes_etag(api_client):
    response = api_client.options(
        "/api/events/1/",
        HTTP_ORIGIN="capacitor://localhost",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="PATCH",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-session-token,if-match",
    )
    assert "if-match" in response["access-control-allow-headers"]
    response = api_client.get("/api/health/", HTTP_ORIGIN="capacitor://localhost")
    assert "etag" in response["access-control-expose-headers"]


@pytest.mark.django_db
def test_updating_a_subtask_does_not_bump_the_parent(auth_client, user):
    parent = TaskFactory(author=user)
    child = TaskFactory(author=user, category=parent.category, parent=parent)
    response = auth_client.patch(f"/api/tasks/{child.id}/", {"status": "finished"})
    assert response.status_code == 200
    parent.refresh_from_db()
    assert parent.version == 1
