import pytest

from librete.contrib.sync.models import Change
from librete.tests.factories import CategoryFactory, EventFactory, NoteFactory, TaskFactory


def sync(client, **params):
    response = client.get("/api/sync/", params)
    assert response.status_code == 200, response.json()
    return response.json()


@pytest.mark.django_db
def test_requires_authentication(api_client):
    assert api_client.get("/api/sync/").status_code == 401


@pytest.mark.django_db
def test_without_since_returns_the_current_cursor(auth_client, user, other_user):
    assert sync(auth_client) == {"cursor": 0, "has_more": False, "changes": []}

    NoteFactory(author=user)
    NoteFactory(author=other_user)  # later, but someone else's
    latest = Change.objects.filter(user=user).latest("id").id
    assert sync(auth_client) == {"cursor": latest, "has_more": False, "changes": []}
    assert sync(auth_client, since=latest) == {"cursor": latest, "has_more": False, "changes": []}


@pytest.mark.django_db
def test_changes_since_a_cursor(auth_client, user):
    category = CategoryFactory(author=user)
    cursor = sync(auth_client)["cursor"]

    note = NoteFactory(author=user, category=category)
    event = EventFactory(author=user, category=category)
    event_id = event.id
    event.delete()

    body = sync(auth_client, since=cursor)
    assert body["has_more"] is False
    assert [(c["type"], c["id"], c["op"]) for c in body["changes"]] == [
        ("notes", note.id, "upsert"),
        ("events", event_id, "delete"),
    ]
    assert body["changes"][1]["data"] is None
    seqs = [c["seq"] for c in body["changes"]]
    assert seqs == sorted(seqs)
    assert body["cursor"] == seqs[-1]
    assert sync(auth_client, since=body["cursor"])["changes"] == []


@pytest.mark.django_db
def test_data_matches_the_item_endpoint(auth_client, user):
    category = CategoryFactory(author=user)
    items = {
        "categories": category,
        "events": EventFactory(author=user, category=category),
        "notes": NoteFactory(author=user, category=category),
        "tasks": TaskFactory(author=user, category=category),
    }
    items["tasks"].name = "Updated"
    items["tasks"].save()

    changes = sync(auth_client, since=0)["changes"]
    assert len(changes) == 4
    for change in changes:
        expected = auth_client.get(f"/api/{change['type']}/{change['id']}/").json()
        assert change["data"] == expected
        assert change["id"] == items[change["type"]].id
    category_data = next(c["data"] for c in changes if c["type"] == "categories")
    assert (category_data["events_count"], category_data["tasks_count"]) == (1, 1)
    task_data = next(c["data"] for c in changes if c["type"] == "tasks")
    assert task_data["version"] == 2


@pytest.mark.django_db
def test_paging(auth_client, user):
    category = CategoryFactory(author=user)
    notes = NoteFactory.create_batch(5, author=user, category=category)
    expected = [category.id] + [note.id for note in notes]

    seen, cursor, pages = [], 0, 0
    while True:
        body = sync(auth_client, since=cursor, limit=2)
        pages += 1
        assert len(body["changes"]) <= 2
        seen += [c["id"] for c in body["changes"]]
        cursor = body["cursor"]
        if not body["has_more"]:
            break
    assert seen == expected
    assert pages == 3
    assert sync(auth_client, since=cursor) == {"cursor": cursor, "has_more": False, "changes": []}


@pytest.mark.django_db
def test_limit_is_capped(auth_client, user):
    NoteFactory(author=user)
    assert len(sync(auth_client, since=0, limit=5000)["changes"]) == 2


@pytest.mark.django_db
def test_types_filter(auth_client, user):
    category = CategoryFactory(author=user)
    event = EventFactory(author=user, category=category)
    note = NoteFactory(author=user, category=category)
    TaskFactory(author=user, category=category)

    body = sync(auth_client, since=0, types="events,notes")
    assert [(c["type"], c["id"]) for c in body["changes"]] == [
        ("events", event.id),
        ("notes", note.id),
    ]
    assert body["cursor"] == body["changes"][-1]["seq"]
    assert sync(auth_client, since=0, types=" tasks ")["changes"][0]["type"] == "tasks"


@pytest.mark.django_db
def test_vanished_upsert_is_reported_as_delete(auth_client, user):
    note = NoteFactory(author=user)
    note_id = note.id
    # Delete without signals (e.g. raw SQL), leaving the upsert row behind.
    type(note).objects.filter(pk=note_id)._raw_delete(using="default")
    change = sync(auth_client, since=0)["changes"][-1]
    assert change == {
        "seq": change["seq"],
        "type": "notes",
        "id": note_id,
        "op": "delete",
        "data": None,
    }


@pytest.mark.django_db
def test_only_the_users_own_changes(auth_client, user, other_user):
    NoteFactory(author=other_user)
    theirs = CategoryFactory(author=other_user)
    theirs.delete()
    assert sync(auth_client, since=0)["changes"] == []
    mine = NoteFactory(author=user)
    ids = {(c["type"], c["id"]) for c in sync(auth_client, since=0)["changes"]}
    assert ids == {("categories", mine.category_id), ("notes", mine.id)}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"since": -1}, "since"),
        ({"since": "abc"}, "since"),
        ({"since": 0, "limit": 0}, "limit"),
        ({"since": 0, "types": "events,widgets"}, "types"),
    ],
)
def test_invalid_parameters(auth_client, params, field):
    response = auth_client.get("/api/sync/", params)
    assert response.status_code == 400
    assert field in response.json()


@pytest.mark.django_db
def test_query_count_does_not_grow_with_items(auth_client, user, django_assert_max_num_queries):
    category = CategoryFactory(author=user)
    for _ in range(10):
        EventFactory(author=user, category=category)
        NoteFactory(author=user, category=category)
    with django_assert_max_num_queries(6):
        assert len(sync(auth_client, since=0)["changes"]) == 21
