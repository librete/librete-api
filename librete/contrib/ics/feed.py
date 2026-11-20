"""A user's events (and optionally dated tasks) as an iCalendar (RFC 5545) calendar.

Used by the subscription feed (`/ics/<token>.ics`) and the data export (`events.ics`).

- Times are written in the author's time zone (`TZID=<IANA name>` + a VTIMEZONE; plain UTC
  `...Z` values when the zone is UTC). Series need this: they repeat at the same local
  wall-clock time across DST changes, exactly like Librete expands them.
- Events lasting whole days in that zone (00:00 to 23:59, as imported all-day events are
  stored) are written as all-day events (`VALUE=DATE`, exclusive DTEND).
- A series carries its RRULE as stored and its EXDATEs; its overrides are VEVENTs with the
  series' UID and a RECURRENCE-ID. Every reminder becomes a VALARM.
- Dated tasks become VEVENTs (not VTODO, which most calendar apps ignore) from their start
  (or due date) to their due date; finished ones are prefixed with a check mark.
- The output only depends on the data (DTSTAMP is the last change), so its hash works as
  an ETag.
"""

from datetime import UTC, date, datetime, time, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from icalendar import Alarm, Calendar, vRecur
from icalendar import Event as VEvent

from librete.contrib.events.models import Event
from librete.contrib.events.recurrence import parse_utc
from librete.contrib.tasks.models import Task
from librete.utils.recurrence import zone

PRODID = "-//Librete//Librete//EN"
CALENDAR_NAME = "Librete"
# How often calendar apps should refresh a subscription (a hint; most decide themselves).
REFRESH_INTERVAL = timedelta(hours=1)
# Local end times that mark an event lasting whole days (imported all-day events end at
# 23:59 on their last day).
ALL_DAY_END_TIMES = {time(23, 59), time(23, 59, 59)}
FINISHED_PREFIX = "✓ "
UTC_NAMES = {"UTC", "Etc/UTC", "Etc/UCT", "Etc/GMT", "GMT", "UCT", "Zulu", "Etc/Zulu"}


def event_uid(event):
    return event.ics_uid or f"librete-event-{event.pk}@{settings.PUBLIC_DOMAIN}"


def task_uid(task):
    return f"librete-task-{task.pk}@{settings.PUBLIC_DOMAIN}"


def all_day_span(start, end, tz):
    """(first day, last day) if [start, end] covers whole days in `tz` (00:00-23:59)."""
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    if (
        local_start.time().replace(microsecond=0) == time(0)
        and local_end.time().replace(microsecond=0) in ALL_DAY_END_TIMES
        and local_end.date() >= local_start.date()
    ):
        return local_start.date(), local_end.date()
    return None


class _Writer:
    def __init__(self, user):
        self.user = user
        self.tz = UTC if user.time_zone in UTC_NAMES else zone(user.time_zone)

    def moment(self, value):
        """A date-time value in the author's zone (UTC values are written with `Z`)."""
        return value.replace(microsecond=0).astimezone(self.tz)

    def local_date(self, value):
        return value.astimezone(self.tz).date()

    @staticmethod
    def _stamp(value):
        return value.astimezone(UTC).replace(microsecond=0)

    def _common(self, component, item, uid, url):
        component.add("uid", uid)
        component.add("dtstamp", self._stamp(item.updated_at))
        component.add("created", self._stamp(item.created_at))
        component.add("last-modified", self._stamp(item.updated_at))
        component.add("sequence", max(item.version - 1, 0))
        component.add("url", url)
        if item.category_id is not None:
            component.add("categories", [item.category.name])

    @staticmethod
    def _alarm(description, trigger):
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", description)
        alarm.add("trigger", trigger)
        return alarm

    def event(self, event, uid, series=None):
        component = VEvent()
        self._common(component, event, uid, f"{settings.FRONTEND_URL}/events/{event.pk}")
        component.add("summary", event.name)
        if event.location:
            component.add("location", event.location)
        if event.description:
            component.add("description", event.description)

        days = all_day_span(event.start_date, event.end_date, self.tz)
        if days is not None:
            component.add("dtstart", days[0])
            component.add("dtend", days[1] + timedelta(days=1))
        else:
            component.add("dtstart", self.moment(event.start_date))
            component.add("dtend", self.moment(event.end_date))

        if series is not None:
            series_all_day = all_day_span(series.start_date, series.end_date, self.tz)
            original = event.original_start
            component.add(
                "recurrence-id",
                self.local_date(original) if series_all_day else self.moment(original),
            )
        elif event.recurrence:
            rule = vRecur.from_ical(event.recurrence)
            if days is not None and "UNTIL" in rule:
                # With a DATE start, UNTIL must be a date too (RFC 5545): the last day on
                # which an occurrence (starting at 00:00) is still within the stored UNTIL.
                rule["UNTIL"] = [self.local_date(rule["UNTIL"][0])]
            component.add("rrule", rule)
            exdates = [parse_utc(value) for value in event.exdates or []]
            if exdates:
                component.add(
                    "exdate",
                    [
                        self.local_date(value) if days is not None else self.moment(value)
                        for value in exdates
                    ],
                )

        for minutes in sorted(set(event.reminders or []), reverse=True):
            component.add_component(self._alarm(event.name, timedelta(minutes=-minutes)))
        return component

    def task(self, task):
        start = task.start_date or task.end_date
        end = None
        if task.start_date and task.end_date and task.end_date > task.start_date:
            end = task.end_date
        finished = task.status == Task.Status.FINISHED

        component = VEvent()
        self._common(component, task, task_uid(task), f"{settings.FRONTEND_URL}/tasks/{task.pk}")
        component.add("summary", f"{FINISHED_PREFIX}{task.name}" if finished else task.name)
        if task.description:
            component.add("description", task.description)

        if end is not None:
            days = all_day_span(start, end, self.tz)
        elif start.astimezone(self.tz).time().replace(microsecond=0) == time(0):
            days = (self.local_date(start), self.local_date(start))
        else:
            days = None
        if days is not None:
            component.add("dtstart", days[0])
            component.add("dtend", days[1] + timedelta(days=1))
            anchor = datetime.combine(days[0], time(0), tzinfo=self.tz)
        else:
            component.add("dtstart", self.moment(start))
            if end is not None:
                component.add("dtend", self.moment(end))
            anchor = start.replace(microsecond=0)

        if not finished:
            due = task.end_date or task.start_date
            for minutes in sorted(set(task.reminders or []), reverse=True):
                trigger = due.replace(microsecond=0) - timedelta(minutes=minutes) - anchor
                component.add_component(self._alarm(task.name, trigger))
        return component


def build_calendar(user, include_tasks=False):
    """The user's events (and dated tasks) as an `icalendar.Calendar`."""
    writer = _Writer(user)
    calendar = Calendar()
    calendar.add("prodid", PRODID)
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", CALENDAR_NAME)
    calendar.add("x-wr-timezone", "UTC" if writer.tz is UTC else user.time_zone)
    calendar.add("refresh-interval", REFRESH_INTERVAL, parameters={"VALUE": "DURATION"})
    calendar.add("x-published-ttl", "PT1H")

    events = list(
        Event.objects.filter(author=user).select_related("category").order_by("start_date", "pk")
    )
    by_id = {event.pk: event for event in events}
    for event in events:
        series = by_id.get(event.recurrence_parent_id)
        if series is not None and series.recurrence:
            calendar.add_component(writer.event(event, event_uid(series), series))
        elif event.recurrence_parent_id is not None:
            # The series stopped repeating: the override is an ordinary event now.
            calendar.add_component(
                writer.event(event, f"librete-event-{event.pk}@{settings.PUBLIC_DOMAIN}")
            )
        else:
            calendar.add_component(writer.event(event, event_uid(event)))

    if include_tasks:
        tasks = (
            Task.objects.filter(author=user)
            .filter(Q(start_date__isnull=False) | Q(end_date__isnull=False))
            .select_related("category")
            .order_by("pk")
        )
        for task in tasks:
            calendar.add_component(writer.task(task))

    if writer.tz is not UTC:
        # VTIMEZONE definitions for the TZIDs used (until 20 years from now).
        calendar.add_missing_timezones(last_date=date(timezone.now().year + 20, 1, 1))
    return calendar


def build_feed(user, include_tasks=False):
    """The calendar as `text/calendar` bytes."""
    return build_calendar(user, include_tasks).to_ical()
