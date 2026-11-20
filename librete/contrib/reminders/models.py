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
