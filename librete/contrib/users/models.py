from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from librete.contrib.reminders.validators import default_reminders, validate_reminders

from .validators import validate_time_zone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email must be set")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """A user who logs in with their email address (there is no username)."""

    username = None
    email = models.EmailField(_("Email address"), unique=True)
    language = models.CharField(
        _("Language"),
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
    )
    time_zone = models.CharField(
        _("Time zone"),
        max_length=64,
        default="UTC",
        validators=[validate_time_zone],
        help_text=_("IANA time zone name, e.g. Europe/Sofia. Used in reminders."),
    )
    default_reminders = models.JSONField(
        _("Default reminders"),
        default=default_reminders,
        blank=True,
        validators=[validate_reminders],
        help_text=_("Minutes before the start, used for new events."),
    )
    default_task_reminders = models.JSONField(
        _("Default task reminders"),
        default=list,
        blank=True,
        validators=[validate_reminders],
        help_text=_("Minutes before the due date, used for new tasks."),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["date_joined"]
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return self.email
