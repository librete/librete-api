"""pg_trgm and GIN trigram indexes for /api/search/ (PostgreSQL only; a no-op elsewhere)."""

from django.db import migrations

# (table, column) pairs searched by librete.contrib.search.views.
INDEXED = [
    ("events_event", "name"),
    ("events_event", "location"),
    ("events_event", "description"),
    ("notes_note", "name"),
    ("notes_note", "text"),
    ("tasks_task", "name"),
    ("tasks_task", "description"),
    ("categories_category", "name"),
    ("categories_category", "description"),
]


def index_name(table, column):
    return f"{table}_{column}_trgm"


def create(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for table, column in INDEXED:
        schema_editor.execute(
            f'CREATE INDEX IF NOT EXISTS "{index_name(table, column)}" '
            f'ON "{table}" USING gin ("{column}" gin_trgm_ops)'
        )


def drop(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, column in INDEXED:
        schema_editor.execute(f'DROP INDEX IF EXISTS "{index_name(table, column)}"')
    # The extension is left in place: other objects may depend on it.


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0007_color"),
        ("events", "0006_version"),
        ("notes", "0005_version"),
        ("tasks", "0005_version"),
    ]

    operations = [migrations.RunPython(create, drop, elidable=False)]
