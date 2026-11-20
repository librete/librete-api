from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from librete.contrib.events.models import Event
from librete.contrib.tasks.models import Task


class ScheduledReminder(models.Model):
    """One pending (or sent) reminder of an event, an occurrence of a series, or a task.

    Derived from `Event.reminders` / `Task.reminders` by `services.sync_event_reminders` and
    `services.sync_task_reminders` (series: occurrences in a rolling window); never edited
    directly. `one_off` rows (snoozed notifications) are created by the notification actions
    and left alone by the sync.
    """

    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="scheduled_reminders",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    task = models.ForeignKey(
        Task,
        verbose_name=_("Task"),
        related_name="scheduled_reminders",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    occurrence_start = models.DateTimeField(
        _("Occurrence start"),
        null=True,
        blank=True,
        help_text=_("For an occurrence of a recurring event: its original start."),
    )
    minutes_before = models.PositiveIntegerField(_("Minutes before"))
    remind_at = models.DateTimeField(_("Remind at"))
    sent_at = models.DateTimeField(_("Sent at"), null=True, blank=True)
    one_off = models.BooleanField(
        _("One-off"), default=False, help_text=_("A snoozed reminder; not derived from the item.")
    )

    class Meta:
        ordering = ["remind_at"]
        verbose_name = _("Scheduled reminder")
        verbose_name_plural = _("Scheduled reminders")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event__isnull=False, task__isnull=True)
                | models.Q(event__isnull=True, task__isnull=False),
                name="reminder_event_or_task",
            ),
            models.UniqueConstraint(
                fields=["event", "minutes_before"],
                condition=models.Q(
                    event__isnull=False, occurrence_start__isnull=True, one_off=False
                ),
                name="unique_event_reminder",
            ),
            models.UniqueConstraint(
                fields=["event", "occurrence_start", "minutes_before"],
                condition=models.Q(occurrence_start__isnull=False, one_off=False),
                name="unique_occurrence_reminder",
            ),
            models.UniqueConstraint(
                fields=["task", "minutes_before"],
                condition=models.Q(task__isnull=False, one_off=False),
                name="unique_task_reminder",
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
        return f"{self.event or self.task} − {self.minutes_before} min"

    @property
    def target_time(self):
        """When the event / occurrence starts or the task is due."""
        if self.event_id is not None:
            return self.occurrence_start or self.event.start_date
        return self.task.end_date or self.task.start_date


class UsedActionToken(models.Model):
    """`jti` of a notification action token that was used (tokens are single-use)."""

    jti = models.UUIDField(_("Token ID"), primary_key=True)
    used_at = models.DateTimeField(_("Used at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Used action token")
        verbose_name_plural = _("Used action tokens")

    def __str__(self):
        return str(self.jti)


class WorkerRun(models.Model):
    """When a periodic job of the reminder worker last ran (e.g. the daily series top-up)."""

    name = models.CharField(_("Name"), max_length=64, primary_key=True)
    last_run_at = models.DateTimeField(_("Last run at"), null=True, blank=True)

    class Meta:
        verbose_name = _("Worker run")
        verbose_name_plural = _("Worker runs")

    def __str__(self):
        return self.name


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
