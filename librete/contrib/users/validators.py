from functools import cache
from zoneinfo import available_timezones

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


@cache
def _time_zones():
    return frozenset(available_timezones())


def validate_time_zone(value):
    """Accept IANA time zone names such as `Europe/Sofia` or `UTC`."""
    if value not in _time_zones():
        raise ValidationError(
            _("“%(value)s” is not a valid time zone."), code="invalid", params={"value": value}
        )
