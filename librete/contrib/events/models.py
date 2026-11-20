from django.db import models
from django.utils.translation import gettext_lazy as _

from librete.contrib.categories.models import Category
from librete.contrib.reminders.validators import validate_reminders
from librete.utils import recurrence
from librete.utils.models import OwnedModel

from .recurrence import validate_exdates


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
    # null (not "") means "doesn't repeat": the API contract returns `null`.
    recurrence = models.CharField(  # noqa: DJ001
        _("Recurrence"),
        max_length=recurrence.MAX_LENGTH,
        null=True,
        blank=True,
        validators=[recurrence.validate_syntax],
        help_text=_("RFC 5545 RRULE without the RRULE: prefix, e.g. FREQ=WEEKLY;BYDAY=MO."),
    )
    exdates = models.JSONField(
        _("Skipped occurrences"),
        default=list,
        blank=True,
        validators=[validate_exdates],
        help_text=_("Original starts (UTC) of the occurrences that are skipped."),
    )
    recurrence_parent = models.ForeignKey(
        "self",
        verbose_name=_("Series"),
        related_name="overrides",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text=_("Set on an event that replaces one occurrence of a recurring event."),
    )
    original_start = models.DateTimeField(
        _("Original start"),
        null=True,
        blank=True,
        help_text=_("The start of the occurrence this event replaces."),
    )

    # Set on the copies that stand for occurrences in expanded lists (see recurrence.py).
    occurrence_start = None
    is_occurrence = False

    class Meta(OwnedModel.Meta):
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        constraints = [
            *OwnedModel.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="event_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(recurrence_parent__isnull=True, original_start__isnull=True)
                | models.Q(
                    recurrence_parent__isnull=False,
                    original_start__isnull=False,
                    recurrence__isnull=True,
                ),
                name="event_override_fields",
            ),
        ]

    def __str__(self):
        return self.name
