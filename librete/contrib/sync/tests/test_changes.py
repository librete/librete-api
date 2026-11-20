"""Every write to a synced model leaves exactly one change-log row per object."""

import importlib

import pytest
from django.apps import apps

from librete.contrib.categories.models import Category, DefaultCategory
from librete.contrib.categories.services import create_default_categories
from librete.contrib.sync.models import Change
from librete.tests.factories import (
    PASSWORD,
    CategoryFactory,
    EventFactory,
    NoteFactory,
    TaskFactory,
    UserFactory,
)

FACTORIES = {
    "categories": CategoryFactory,
    "events": EventFactory,
    "notes": NoteFactory,
    "tasks": TaskFactory,
}


def log(user):
    return list(
        Change.objects.filter(user=user).order_by("id").values_list("type", "object_id", "op")
    )


@pytest.mark.django_db
@pytest.mark.parametrize("type", FACTORIES)
def test_create_update_delete_keep_one_row_per_object(user, type):
    item = FACTORIES[type](author=user)
    created = Change.objects.get(user=user, type=type, object_id=item.pk)
    assert created.op == "upsert"

    item.name = "Renamed"
    item.save()
    updated = Change.objects.get(user=user, type=type, object_id=item.pk)
    assert updated.op == "upsert"
    assert updated.id > created.id

    pk = item.pk
    item.delete()
    deleted = Change.objects.get(user=user, type=type, object_id=pk)
    assert deleted.op == "delete"
    assert deleted.id > updated.id


@pytest.mark.django_db
def test_latest_change_moves_to_the_end(user):
    first = NoteFactory(author=user)
    second = NoteFactory(author=user, category=first.category)
    first.save()
    notes = [row for row in log(user) if row[0] == "notes"]
    assert notes == [("notes", second.pk, "upsert"), ("notes", first.pk, "upsert")]


@pytest.mark.django_db
def test_api_writes_are_recorded(auth_client, user):
    category = CategoryFactory(author=user)
    note_id = auth_client.post(
        "/api/notes/", {"name": "n", "category": category.id, "text": "t"}
    ).json()["id"]
    auth_client.patch(f"/api/notes/{note_id}/", {"name": "m"})
    assert log(user)[-1] == ("notes", note_id, "upsert")
    auth_client.delete(f"/api/notes/{note_id}/")
    assert log(user)[-1] == ("notes", note_id, "delete")
    # A rejected (409) write records nothing.
    before = log(user)
    auth_client.patch(f"/api/categories/{category.id}/", {"name": "x"}, HTTP_IF_MATCH="9")
    assert log(user) == before


@pytest.mark.django_db
def test_deleting_a_category_records_its_cascaded_items(user):
    category = CategoryFactory(author=user)
    event = EventFactory(author=user, category=category)
    note = NoteFactory(author=user, category=category)
    task = TaskFactory(author=user, category=category)
    other = CategoryFactory(author=user)
    subtask = TaskFactory(author=user, category=other, parent=task)
    kept = NoteFactory(author=user, category=other)
    category_id = category.pk

    category.delete()

    deletes = {(t, pk) for t, pk, op in log(user) if op == "delete"}
    assert deletes == {
        ("categories", category_id),
        ("events", event.pk),
        ("notes", note.pk),
        ("tasks", task.pk),
        ("tasks", subtask.pk),  # a subtask in another category, deleted with its parent
    }
    assert ("notes", kept.pk, "upsert") in log(user)


@pytest.mark.django_db
def test_deleting_a_task_records_its_subtasks(auth_client, user):
    parent = TaskFactory(author=user)
    child = TaskFactory(author=user, category=parent.category, parent=parent)
    grandchild = TaskFactory(author=user, category=parent.category, parent=child)
    assert auth_client.delete(f"/api/tasks/{parent.id}/").status_code == 204
    deletes = {pk for t, pk, op in log(user) if op == "delete"}
    assert deletes == {parent.pk, child.pk, grandchild.pk}


@pytest.mark.django_db
def test_queryset_delete_is_recorded(user):
    notes = NoteFactory.create_batch(2, author=user)
    type(notes[0]).objects.filter(author=user).delete()
    deletes = {pk for t, pk, op in log(user) if op == "delete"}
    assert deletes == {note.pk for note in notes}


@pytest.mark.django_db
def test_changes_belong_to_the_author(user, other_user):
    mine = NoteFactory(author=user)
    NoteFactory(author=other_user)
    assert ("notes", mine.pk, "upsert") in log(user)
    assert all(pk != mine.pk for t, pk, op in log(other_user) if t == "notes")


@pytest.mark.django_db
def test_deleting_the_user_deletes_the_log(user):
    EventFactory(author=user)
    user.delete()
    assert not Change.objects.exists()


@pytest.mark.django_db
def test_default_categories_are_recorded(db):
    DefaultCategory.objects.create(name="Work")
    user = UserFactory()
    categories = create_default_categories(user)
    assert {(t, pk) for t, pk, op in log(user)} == {("categories", c.pk) for c in categories}
    assert Category.objects.filter(author=user).count() == len(categories) > 0


@pytest.mark.django_db
def test_backfill_migration_adds_missing_rows(user):
    note = NoteFactory(author=user)
    event = EventFactory(author=user)
    Change.objects.filter(type="notes").delete()
    migration = importlib.import_module("librete.contrib.sync.migrations.0002_backfill")
    migration.backfill(apps, None)
    assert ("notes", note.pk, "upsert") in log(user)
    assert Change.objects.filter(type="events", object_id=event.pk).count() == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_cascading_deletes_commit(client_for):
    """Foreign keys are checked at commit, which the other (rolled back) tests never reach."""
    user = UserFactory()
    client = client_for(user)
    category = CategoryFactory(author=user)
    parent = TaskFactory(author=user, category=category)
    TaskFactory(author=user, parent=parent)  # in another category
    EventFactory(author=user, category=category)

    assert client.delete(f"/api/categories/{category.id}/").status_code == 204
    assert Change.objects.filter(user=user, op="delete").count() == 4

    response = client.post("/api/users/me/delete/", {"password": PASSWORD})
    assert response.status_code == 204
    assert not Change.objects.exists()
