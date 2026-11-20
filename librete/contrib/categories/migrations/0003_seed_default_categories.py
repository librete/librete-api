from django.db import migrations

DEFAULTS = [
    {
        "en": ("Personal", "Personal plans and errands"),
        "bg": ("Лични", "Лични планове и задачи"),
    },
    {
        "en": ("Work", "Work-related events, notes and tasks"),
        "bg": ("Работа", "Събития, бележки и задачи, свързани с работата"),
    },
    {
        "en": ("Home", "Household chores and family"),
        "bg": ("Дом", "Домакинство и семейство"),
    },
]


def seed(apps, schema_editor):
    DefaultCategory = apps.get_model("categories", "DefaultCategory")
    Translation = apps.get_model("categories", "DefaultCategoryTranslation")
    if DefaultCategory.objects.exists():
        return
    for item in DEFAULTS:
        category = DefaultCategory.objects.create()
        for language, (name, description) in item.items():
            Translation.objects.create(
                master=category, language_code=language, name=name, description=description
            )


def unseed(apps, schema_editor):
    apps.get_model("categories", "DefaultCategory").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("categories", "0002_initial")]

    operations = [migrations.RunPython(seed, unseed)]
