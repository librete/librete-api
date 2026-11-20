"""Validation of reminder offsets ("minutes before the start"), shared by events and users."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MAX_REMINDERS = 5
MAX_MINUTES_BEFORE = 40320  # 4 weeks


def default_reminders():
    return [15]


def normalize_reminders(value):
    """Return the offsets without duplicates, sorted descending (earliest reminder first).

    Raises `ValidationError` unless `value` is a list of at most `MAX_REMINDERS` distinct
    integers between 0 and `MAX_MINUTES_BEFORE`.
    """
    if not isinstance(value, list):
        raise ValidationError(_("Expected a list of minutes."), code="invalid")
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValidationError(_("Reminders must be whole numbers of minutes."), code="invalid")
        if not 0 <= item <= MAX_MINUTES_BEFORE:
            raise ValidationError(
                _("Reminders must be between 0 and %(max)s minutes before the start."),
                code="out_of_range",
                params={"max": MAX_MINUTES_BEFORE},
            )
    result = sorted(set(value), reverse=True)
    if len(result) > MAX_REMINDERS:
        raise ValidationError(
            _("At most %(max)s reminders are allowed."),
            code="too_many",
            params={"max": MAX_REMINDERS},
        )
    return result


def validate_reminders(value):
    normalize_reminders(value)
