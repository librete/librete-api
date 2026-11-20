from django.db import models
from django.utils.translation import gettext_lazy as _

from librete.contrib.categories.models import Category
from librete.contrib.reminders.validators import validate_reminders
from librete.utils.models import OwnedModel


class Event(OwnedModel):
    name = models.CharField(_("Name"), max_length=254)
    category = models.ForeignKey(
        Category, verbose_name=_("Category"), related_name="events", on_delete=models.CASCADE
    )
    start_date = models.DateTimeField(_("Start date"))
    end_date = models.DateTimeField(_("End date"))
    location = models.CharField(_("Location"), max_length=254, blank=True)
    description = models.TextField(_("Description"), blank=True)
    reminders = models.JSONField(
        _("Reminders"),
        default=list,
        blank=True,
        validators=[validate_reminders],
        help_text=_("Minutes before the start, e.g. [60, 15]."),
    )

    class Meta(OwnedModel.Meta):
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="event_end_after_start",
            ),
        ]

    def __str__(self):
        return self.name
