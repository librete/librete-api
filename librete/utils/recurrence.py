"""RFC 5545 recurrence rules (RRULE bodies) shared by recurring events and repeating tasks.

Semantics (the app implements the same, see `events/tests/rrule_vectors.json`):
- the rule is expanded by python-dateutil with DTSTART = the item's start converted to the
  author's time zone (microseconds dropped), so the local wall-clock time is kept across
  DST changes;
- a local time that doesn't exist (spring forward) uses the offset from before the change
  (03:30 in Europe/Sofia on the last Sunday of March is 04:30 summer time); an ambiguous
  one (fall back) is the first of the two;
- as in dateutil (and rrule.js), DTSTART is only an occurrence if it matches the rule.
"""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import rrule
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MAX_LENGTH = 500
FREQUENCIES = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
# Rule parts that are accepted. BYHOUR, BYMINUTE and BYSECOND are not: with them a rule
# could repeat several times a day, which the supported frequencies exclude.
PARTS = {
    "FREQ",
    "INTERVAL",
    "COUNT",
    "UNTIL",
    "WKST",
    "BYSETPOS",
    "BYMONTH",
    "BYMONTHDAY",
    "BYYEARDAY",
    "BYWEEKNO",
    "BYDAY",
}
PART_RE = re.compile(r"([A-Z]+)=([A-Z0-9,+\-]+)")
# Allowed ranges of numeric list parts: (lowest, highest, negative values allowed).
NUMBER_RANGES = {
    "BYMONTH": (1, 12, False),
    "BYMONTHDAY": (1, 31, True),
    "BYYEARDAY": (1, 366, True),
    "BYWEEKNO": (1, 53, True),
    "BYSETPOS": (1, 366, True),
}
UNTIL_RE = re.compile(r"\d{8}T\d{6}Z")
# A rule without an end must produce an occurrence within this time from DTSTART (rules
# like "every 30 February" are rejected instead of being iterated forever).
HORIZON = timedelta(days=366 * 10)

INVALID = _("Enter a valid recurrence rule, e.g. FREQ=WEEKLY;BYDAY=MO.")


def zone(name):
    """The time zone with this IANA name, or UTC when it is unknown."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _parts(value):
    parts = {}
    for item in value.split(";"):
        match = PART_RE.fullmatch(item)
        if match is None:
            raise ValidationError(INVALID, code="invalid")
        name, part_value = match.groups()
        if name not in PARTS or name in parts:
            raise ValidationError(INVALID, code="invalid")
        parts[name] = part_value
    for name, (lowest, highest, negative) in NUMBER_RANGES.items():
        for number in parts.get(name, "").split(",") if name in parts else ():
            try:
                number = int(number)
            except ValueError:
                raise ValidationError(INVALID, code="invalid") from None
            if not (lowest <= abs(number) <= highest and (negative or number > 0)):
                raise ValidationError(INVALID, code="invalid")
    if parts.get("FREQ") not in FREQUENCIES:
        raise ValidationError(
            _("The frequency must be DAILY, WEEKLY, MONTHLY or YEARLY."), code="frequency"
        )
    if "UNTIL" in parts and not UNTIL_RE.fullmatch(parts["UNTIL"]):
        raise ValidationError(
            _("UNTIL must be a UTC date and time such as 20301231T235959Z."), code="until"
        )
    if "COUNT" in parts and "UNTIL" in parts:
        raise ValidationError(_("Use either COUNT or UNTIL, not both."), code="count_until")
    return parts


def build(value, dtstart, tz):
    """The dateutil rule for `value` (already validated) starting at `dtstart` in `tz`."""
    local = dtstart.astimezone(tz).replace(microsecond=0)
    return rrule.rrulestr(value, dtstart=local)


def normalize(value, dtstart, tz):
    """Validate an RRULE body against its DTSTART and return it upper-cased (or None).

    Raises `ValidationError` for anything but `NAME=VALUE` parts separated by `;` (no
    `RRULE:` prefix), unsupported frequencies or parts, invalid values, COUNT together with
    UNTIL, and rules without an end that produce no occurrence within ten years.
    """
    if value is None:
        return None
    value = value.strip().upper()
    if not value:
        return None
    if len(value) > MAX_LENGTH:
        raise ValidationError(INVALID, code="invalid")
    parts = _parts(value)
    for name in ("COUNT", "INTERVAL"):
        if name in parts and not (parts[name].isdigit() and int(parts[name]) >= 1):
            raise ValidationError(INVALID, code="invalid")
    try:
        rule = build(value, dtstart, tz)
        horizon = dtstart.astimezone(tz) + HORIZON
        until = None
        if "UNTIL" in parts:
            until = datetime.strptime(parts["UNTIL"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        empty = False
        if until is None or until > horizon:
            empty = next(iter(rule.replace(count=None, until=horizon)), None) is None
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        raise ValidationError(INVALID, code="invalid") from exc
    if empty:
        raise ValidationError(_("The recurrence rule never produces an occurrence."), code="empty")
    return value


def validate_syntax(value):
    """Model field validator: checks the rule against an arbitrary DTSTART (UTC, now)."""
    from django.utils import timezone

    normalize(value, timezone.now(), UTC)


def starts_between(value, dtstart, tz, after, before):
    """UTC starts of the rule's occurrences in [after, before] (both inclusive)."""
    if after > before:
        return []
    rule = build(value, dtstart, tz)
    return [start.astimezone(UTC) for start in rule.between(after, before, inc=True)]


def next_after(value, dtstart, tz):
    """The first occurrence strictly after `dtstart` (UTC), or None when the rule ended."""
    rule = build(value, dtstart, tz)
    following = rule.after(dtstart.astimezone(tz).replace(microsecond=0), inc=False)
    return None if following is None else following.astimezone(UTC)


def format_utc(value):
    """`YYYY-MM-DDTHH:MM:SSZ`."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
