"""Expansion of recurring events (series) into occurrences.

A series is an event with `recurrence`. Its occurrences start at the rule's starts (see
`librete.utils.recurrence`, DTSTART = `start_date` in the author's time zone) and last
`end_date - start_date`. An occurrence whose original start is in `exdates`, or that has an
override (an event with `recurrence_parent` = the series and `original_start` = that
start), is skipped: the override, a stored event, stands for it.
"""

import copy
from datetime import UTC

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from librete.utils import recurrence


def _as_utc(value):
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            raise ValueError(value)
        value = parsed
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0)


def normalize_exdates(values):
    """Sorted, deduplicated `YYYY-MM-DDTHH:MM:SSZ` strings (UTC, whole seconds)."""
    if not isinstance(values, list):
        raise ValidationError(_("Expected a list of date-times."), code="invalid")
    try:
        instants = {_as_utc(value) for value in values}
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(_("Expected a list of date-times."), code="invalid") from exc
    return [recurrence.format_utc(value) for value in sorted(instants)]


def validate_exdates(value):
    normalize_exdates(value)


def excluded_starts(event):
    return {_as_utc(value) for value in event.exdates or []}


def occurrences(series, tz, range_start, range_end, skip=frozenset()):
    """(start, end) of the series' occurrences overlapping [range_start, range_end].

    An occurrence overlaps when it starts at or before `range_end` and ends at or after
    `range_start` (the same rule as `start_date__lte` / `end_date__gte`). Starts in `skip`
    or in the series' `exdates` are left out.
    """
    duration = series.end_date - series.start_date
    skipped = excluded_starts(series) | set(skip)
    starts = recurrence.starts_between(
        series.recurrence, series.start_date, tz, range_start - duration, range_end
    )
    return [(start, start + duration) for start in starts if start not in skipped]


def occurrence_instance(series, start, end):
    """A copy of the series standing for one occurrence (for serialization only)."""
    instance = copy.copy(series)
    instance.start_date = start
    instance.end_date = end
    instance.occurrence_start = start
    instance.is_occurrence = True
    return instance


def overridden_starts(overrides):
    """{series id: {original starts}} for the given override events."""
    result = {}
    for override in overrides:
        result.setdefault(override.recurrence_parent_id, set()).add(
            _as_utc(override.original_start)
        )
    return result


def parse_utc(value):
    """A stored exdate / any datetime as an aware UTC datetime in whole seconds."""
    return _as_utc(value)
