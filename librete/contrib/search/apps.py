from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SearchConfig(AppConfig):
    name = "librete.contrib.search"
    verbose_name = _("Search")
