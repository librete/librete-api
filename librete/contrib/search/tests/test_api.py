from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from librete.tests.factories import CategoryFactory, EventFactory, NoteFactory, TaskFactory

postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="trigram ranking needs PostgreSQL with pg_trgm (SQLite only does icontains)",
)
sqlite_only = pytest.mark.skipif(
    connection.vendor == "postgresql", reason="the icontains fallback is used on SQLite only"
)


def search(client, **params):
    response = client.get("/api/search/", params)
    assert response.status_code == 200, response.json()
    return response.json()


def found(body):
    return [(result["type"], result["id"]) for result in body["results"]]


@pytest.mark.django_db
def test_requires_authentication(api_client):
    assert api_client.get("/api/search/", {"q": "milk"}).status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("q", ["", "m", "  m  "])
def test_query_needs_two_characters(auth_client, q):
    response = auth_client.get("/api/search/", {"q": q})
    assert response.status_code == 400
    assert "q" in response.json()


@pytest.mark.django_db
def test_missing_query_is_rejected(auth_client):
    assert auth_client.get("/api/search/").status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params", [{"types": "events,people"}, {"limit": "0"}, {"limit": "x"}, {"category": "x"}]
)
def test_invalid_parameters(auth_client, params):
    assert auth_client.get("/api/search/", {"q": "milk", **params}).status_code == 400


@pytest.mark.django_db
def test_searches_every_type_and_field(auth_client, user):
    category = CategoryFactory(author=user, name="Shopping", description="Buy milk weekly")
    note = NoteFactory(author=user, category=category, name="List", text="milk, bread")
    task = TaskFactory(author=user, category=category, name="Get MILK", description="")
    event = EventFactory(
        author=user, category=category, name="Farm", location="Milk farm", description=""
    )
    by_description = EventFactory(
        author=user, category=category, name="Visit", location="", description="fresh milk"
    )
    NoteFactory(author=user, category=category, name="Unrelated", text="nothing here")

    body = search(auth_client, q="  milk ")

    assert body["query"] == "milk"
    assert set(found(body)) == {
        ("categories", category.id),
        ("notes", note.id),
        ("tasks", task.id),
        ("events", event.id),
        ("events", by_description.id),
    }
    assert body["counts"] == {"events": 2, "notes": 1, "tasks": 1, "categories": 1}


@pytest.mark.django_db
def test_items_are_serialized_like_the_detail_endpoint(auth_client, user):
    category = CategoryFactory(author=user, name="Groceries", color="#00ff00")
    NoteFactory(author=user, category=category, text="milk")
    note = NoteFactory(author=user, category=category, name="Milk")

    body = search(auth_client, q="milk", types="notes,categories")
    items = {(r["type"], r["id"]): r["item"] for r in body["results"]}
    assert items[("notes", note.id)] == auth_client.get(f"/api/notes/{note.id}/").json()

    body = search(auth_client, q="groceries")
    assert body["results"][0]["item"] == auth_client.get(f"/api/categories/{category.id}/").json()
    assert body["results"][0]["item"]["notes_count"] == 2


@pytest.mark.django_db
def test_types_filter(auth_client, user):
    note = NoteFactory(author=user, name="Milk")
    TaskFactory(author=user, name="Milk")
    body = search(auth_client, q="milk", types="notes")
    assert found(body) == [("notes", note.id)]
    assert body["counts"] == {"notes": 1}


@pytest.mark.django_db
def test_category_filter_limits_items_but_not_categories(auth_client, user):
    home = CategoryFactory(author=user, name="Milk run")
    work = CategoryFactory(author=user, name="Work")
    in_home = NoteFactory(author=user, category=home, name="Milk")
    NoteFactory(author=user, category=work, name="Milk")
    in_home_task = TaskFactory(author=user, category=home, name="Milk")
    EventFactory(author=user, category=work, name="Milk")

    body = search(auth_client, q="milk", category=home.id)

    assert set(found(body)) == {
        ("notes", in_home.id),
        ("tasks", in_home_task.id),
        ("categories", home.id),
    }
    assert body["counts"] == {"events": 0, "notes": 1, "tasks": 1, "categories": 1}


@pytest.mark.django_db
def test_limit_applies_per_type_and_counts_ignore_it(auth_client, user):
    category = CategoryFactory(author=user)
    for _ in range(4):
        NoteFactory(author=user, category=category, name="Milk")
    for _ in range(3):
        TaskFactory(author=user, category=category, name="Milk")

    body = search(auth_client, q="milk", limit=2)
    types = [result["type"] for result in body["results"]]
    assert sorted(types) == ["notes", "notes", "tasks", "tasks"]
    assert body["counts"]["notes"] == 4
    assert body["counts"]["tasks"] == 3


@pytest.mark.django_db
def test_limit_is_capped(auth_client, user):
    category = CategoryFactory(author=user)
    for _ in range(52):
        NoteFactory(author=user, category=category, name="Milk")
    body = search(auth_client, q="milk", types="notes", limit=500)
    assert len(body["results"]) == 50
    assert body["counts"]["notes"] == 52


@pytest.mark.django_db
def test_other_users_data_is_never_found(auth_client, user, other_user):
    mine = NoteFactory(author=user, name="Milk")
    NoteFactory(author=other_user, name="Milk")
    TaskFactory(author=other_user, name="Milk")
    theirs = CategoryFactory(author=other_user, name="Milk")
    EventFactory(author=other_user, category=theirs, name="Milk")

    body = search(auth_client, q="milk")
    assert found(body) == [("notes", mine.id)]
    assert search(auth_client, q="milk", category=theirs.id)["results"] == []


@pytest.mark.django_db
def test_cyrillic(auth_client, user):
    note = NoteFactory(author=user, name="Списък", text="Да купя мляко и хляб")
    NoteFactory(author=user, name="Друго", text="нищо")
    assert found(search(auth_client, q="мляко")) == [("notes", note.id)]


@sqlite_only
@pytest.mark.django_db
def test_sqlite_scores_every_match_one_and_orders_by_updated_at(auth_client, user):
    category = CategoryFactory(author=user, name="Misc")
    older = NoteFactory(author=user, category=category, name="Milk")
    newer = TaskFactory(author=user, category=category, name="Milk")
    older.save()  # now the most recently updated
    body = search(auth_client, q="milk")
    assert found(body) == [("notes", older.id), ("tasks", newer.id)]
    assert {result["score"] for result in body["results"]} == {1.0}


@postgres_only
@pytest.mark.django_db
def test_ranking_by_similarity(auth_client, user):
    category = CategoryFactory(author=user, name="Box", description="")
    contains = NoteFactory(
        author=user,
        category=category,
        name="Reminder",
        text="Remember the long shopping list that includes buttermilk somewhere",
    )
    exact = NoteFactory(author=user, category=category, name="milk", text="")
    word = TaskFactory(author=user, category=category, name="milky way", description="")

    body = search(auth_client, q="milk")

    assert found(body) == [("notes", exact.id), ("tasks", word.id), ("notes", contains.id)]
    assert [result["score"] for result in body["results"]] == [1.0, 0.8, 0.6]


@postgres_only
@pytest.mark.django_db
def test_containing_the_query_scores_at_least_one_half(auth_client, user):
    category = CategoryFactory(author=user, name="Box", description="")
    # word_similarity("xyz", "abcxyzdef") is 0.25: below the threshold, but it contains it.
    note = NoteFactory(author=user, category=category, name="Code", text="abcXYZdef")
    body = search(auth_client, q="xyz")
    assert found(body) == [("notes", note.id)]
    assert body["results"][0]["score"] == 0.5


@postgres_only
@pytest.mark.django_db
def test_typo_tolerance(auth_client, user):
    note = NoteFactory(author=user, name="Dentist appointment", text="")
    event = EventFactory(author=user, name="Concert", location="Philharmonic", description="")
    NoteFactory(author=user, name="Groceries", text="")

    assert found(search(auth_client, q="dentsit")) == [("notes", note.id)]
    assert found(search(auth_client, q="philharmnic")) == [("events", event.id)]


@postgres_only
@pytest.mark.django_db
def test_cyrillic_is_case_insensitive_and_typo_tolerant(auth_client, user):
    note = NoteFactory(author=user, name="Зъболекар", text="")
    task = TaskFactory(author=user, name="Купи МЛЯКО", description="")

    assert found(search(auth_client, q="зъболекр")) == [("notes", note.id)]
    assert found(search(auth_client, q="мляко")) == [("tasks", task.id)]


@postgres_only
@pytest.mark.django_db
def test_equal_scores_are_ordered_by_updated_at(auth_client, user):
    category = CategoryFactory(author=user, name="Box", description="")
    first = NoteFactory(author=user, category=category, name="milk", text="")
    second = TaskFactory(author=user, category=category, name="milk", description="")
    first.updated_at = timezone.now() - timedelta(days=1)
    first.save()  # auto_now: becomes the newest
    body = search(auth_client, q="milk")
    assert found(body) == [("notes", first.id), ("tasks", second.id)]


@pytest.mark.django_db
def test_errors_are_translated(auth_client):
    response = auth_client.get("/api/search/", {"q": "м"}, HTTP_ACCEPT_LANGUAGE="bg")
    assert response.json()["q"] == ["Въведете поне 2 знака."]
