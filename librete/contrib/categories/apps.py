from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CategoriesConfig(AppConfig):
    name = "librete.contrib.categories"
    verbose_name = _("Categories")

    def ready(self):
        from . import signals  # noqa: F401
