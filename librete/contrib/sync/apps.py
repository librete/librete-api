from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SyncConfig(AppConfig):
    name = "librete.contrib.sync"
    verbose_name = _("Sync")

    def ready(self):
        from . import signals  # noqa: F401
