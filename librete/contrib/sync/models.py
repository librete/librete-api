from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Change(models.Model):
    """The per-user change log behind `GET /api/sync/`.

    There is exactly one row per (user, type, object_id): every change deletes the old row
    and inserts a new one, so `id` (the sync cursor) orders objects by their latest change.
    Rows are written by signals (see `signals.py`) in the same transaction as the change.
    """

    class Type(models.TextChoices):
        CATEGORIES = "categories", _("Categories")
        EVENTS = "events", _("Events")
        NOTES = "notes", _("Notes")
        TASKS = "tasks", _("Tasks")

    class Op(models.TextChoices):
        UPSERT = "upsert", _("Created or updated")
        DELETE = "delete", _("Deleted")

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("User"),
        related_name="changes",
        on_delete=models.CASCADE,
    )
    type = models.CharField(_("Type"), max_length=16, choices=Type)
    object_id = models.BigIntegerField(_("Object ID"))
    op = models.CharField(_("Operation"), max_length=8, choices=Op)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Change")
        verbose_name_plural = _("Changes")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type", "object_id"], name="sync_change_unique_object"
            ),
        ]
        indexes = [models.Index(fields=["user", "id"], name="sync_change_user_id")]

    def __str__(self):
        return f"{self.op} {self.type} {self.object_id}"
