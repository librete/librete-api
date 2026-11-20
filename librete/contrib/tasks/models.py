from django.db import models, router, transaction
from django.utils.translation import gettext_lazy as _

from librete.contrib.categories.models import Category
from librete.utils import recurrence
from librete.utils.models import OwnedModel, lock_owner


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
    # null (not "") means "doesn't repeat": the API contract returns `null`.
    repeat = models.CharField(  # noqa: DJ001
        _("Repeat"),
        max_length=recurrence.MAX_LENGTH,
        null=True,
        blank=True,
        validators=[recurrence.validate_syntax],
        help_text=_(
            "RFC 5545 RRULE without the RRULE: prefix. Completing the task creates the next one."
        ),
    )

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

    def save(self, *args, **kwargs):
        """Completing a repeating task also creates its next instance (same transaction)."""
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        update_fields = kwargs.get("update_fields")
        with transaction.atomic(using=using):
            completing = False
            if (
                not self._state.adding
                and self.repeat
                and self.status == self.Status.FINISHED
                and (update_fields is None or "status" in update_fields)
            ):
                lock_owner(self.author_id, using)
                previous = (
                    type(self)
                    ._base_manager.using(using)
                    .filter(pk=self.pk)
                    .values_list("status", flat=True)
                    .first()
                )
                completing = previous is not None and previous != self.Status.FINISHED
            super().save(*args, **kwargs)
            if completing:
                from .services import create_next_instance

                create_next_instance(self, using=using)
