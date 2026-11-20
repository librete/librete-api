"""Give every existing item an upsert row, so `since=0` covers data from before the log."""

from django.db import migrations

TYPES = (
    ("categories", "categories", "Category"),
    ("events", "events", "Event"),
    ("notes", "notes", "Note"),
    ("tasks", "tasks", "Task"),
)


def backfill(apps, schema_editor):
    Change = apps.get_model("sync", "Change")
    for type, app_label, model_name in TYPES:
        model = apps.get_model(app_label, model_name)
        rows = model.objects.order_by("pk").values_list("author_id", "pk").iterator()
        batch = []
        for author_id, pk in rows:
            batch.append(Change(user_id=author_id, type=type, object_id=pk, op="upsert"))
            if len(batch) >= 1000:
                Change.objects.bulk_create(batch, ignore_conflicts=True)
                batch = []
        Change.objects.bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("sync", "0001_initial"),
        ("categories", "0006_version"),
        ("events", "0006_version"),
        ("notes", "0005_version"),
        ("tasks", "0005_version"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
