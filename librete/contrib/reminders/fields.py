from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .validators import MAX_MINUTES_BEFORE, normalize_reminders


class RemindersField(serializers.ListField):
    """A list of minutes before the start, e.g. `[60, 15]`.

    Duplicates are removed and the result is sorted descending; at most 5 entries,
    each 0..40320.
    """

    child = serializers.IntegerField(min_value=0, max_value=MAX_MINUTES_BEFORE)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return normalize_reminders(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
