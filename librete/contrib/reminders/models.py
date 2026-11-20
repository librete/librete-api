from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from librete.contrib.events.models import Event


class ScheduledReminder(models.Model):
    """One pending (or sent) reminder of an event, derived from `Event.reminders`.

    Maintained by `services.sync_event_reminders`; never edited directly.
    """

    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="scheduled_reminders",
        on_delete=models.CASCADE,
    )
    minutes_before = models.PositiveIntegerField(_("Minutes before"))
    remind_at = models.DateTimeField(_("Remind at"))
    sent_at = models.DateTimeField(_("Sent at"), null=True, blank=True)

    class Meta:
        ordering = ["remind_at"]
        verbose_name = _("Scheduled reminder")
        verbose_name_plural = _("Scheduled reminders")
        constraints = [
            models.UniqueConstraint(
                fields=["event", "minutes_before"], name="unique_event_reminder"
            ),
        ]
        indexes = [
            models.Index(
                fields=["remind_at"],
                condition=models.Q(sent_at__isnull=True),
                name="pending_reminder_idx",
            ),
        ]

    def __str__(self):
        return f"{self.event} − {self.minutes_before} min"


class PushSubscription(models.Model):
    """A browser's Web Push subscription (the PWA); reminders are pushed to it."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("User"),
        related_name="push_subscriptions",
        on_delete=models.CASCADE,
    )
    endpoint = models.URLField(_("Endpoint"), max_length=500, unique=True)
    p256dh = models.CharField(_("P-256 public key"), max_length=255)
    auth = models.CharField(_("Auth secret"), max_length=255)
    user_agent = models.CharField(_("User agent"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    last_used_at = models.DateTimeField(_("Last used at"), null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Push subscription")
        verbose_name_plural = _("Push subscriptions")

    def __str__(self):
        return f"{self.user} – {self.user_agent or self.endpoint[:60]}"

    @property
    def subscription_info(self):
        """The subscription in the format `pywebpush.webpush` expects."""
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}
