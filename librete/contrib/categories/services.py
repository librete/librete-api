from .models import Category, DefaultCategory


def create_default_categories(user):
    """Give `user` their own copy of every default category, in their language."""
    language = getattr(user, "language", None)
    categories = []
    for default in DefaultCategory.objects.prefetch_related("translations"):
        default.set_current_language(language)
        categories.append(
            Category(
                author=user,
                name=default.safe_translation_getter("name", any_language=True) or "",
                description=default.safe_translation_getter("description", any_language=True)
                or "",
            )
        )
    return Category.objects.bulk_create(categories)
