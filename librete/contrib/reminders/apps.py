from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RemindersConfig(AppConfig):
    name = "librete.contrib.reminders"
    verbose_name = _("Reminders")

    def ready(self):
        from . import signals  # noqa: F401
