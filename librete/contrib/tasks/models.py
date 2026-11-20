from django.db import models
from django.utils.translation import gettext_lazy as _

from librete.contrib.categories.models import Category
from librete.utils.models import OwnedModel


class Task(OwnedModel):
    class Priority(models.TextChoices):
        HIGH = "high", _("High")
        MEDIUM = "medium", _("Medium")
        LOW = "low", _("Low")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        FINISHED = "finished", _("Finished")

    name = models.CharField(_("Name"), max_length=254)
    category = models.ForeignKey(
        Category, verbose_name=_("Category"), related_name="tasks", on_delete=models.CASCADE
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("Parent task"),
        related_name="subtasks",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    start_date = models.DateTimeField(_("Start date"), blank=True, null=True)
    end_date = models.DateTimeField(_("End date"), blank=True, null=True)
    description = models.TextField(_("Description"), blank=True)
    priority = models.CharField(_("Priority"), max_length=16, choices=Priority, blank=True)
    status = models.CharField(_("Status"), max_length=16, choices=Status, default=Status.ACTIVE)

    class Meta(OwnedModel.Meta):
        verbose_name = _("Task")
        verbose_name_plural = _("Tasks")
        constraints = [
            *OwnedModel.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(start_date__isnull=True)
                | models.Q(end_date__isnull=True)
                | models.Q(end_date__gte=models.F("start_date")),
                name="task_end_after_start",
            ),
        ]

    def __str__(self):
        return self.name
