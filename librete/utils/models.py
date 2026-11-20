from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimestampModel(models.Model):
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(TimestampModel):
    """Base for user-owned records. Reverse accessors are named after the app: `user.events`."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Author"),
        related_name="%(app_label)s",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True
        ordering = ["created_at"]
