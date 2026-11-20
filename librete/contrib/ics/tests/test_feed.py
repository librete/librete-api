from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
import time_machine
from dateutil import rrule
from django.core.cache import cache
from icalendar import Calendar

from librete.contrib.ics.views import FeedTokenThrottle
from librete.contrib.tasks.models import Task
from librete.tests.factories import CategoryFactory, EventFactory, TaskFactory

SOFIA = ZoneInfo("Europe/Sofia")
URL = "/api/users/me/ics/"


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def feed_path(url):
    return urlsplit(url).path


def enable_feed(client, **data):
    response = client.post(URL, data)
    assert response.status_code == 200, response.content
    return response.json()


def fetch(api_client, url, **headers):
    return api_client.get(feed_path(url), **headers)


def parse(response):
    assert response.status_code == 200, response.content
    return Calendar.from_ical(response.content)


def vevents(calendar):
    return list(calendar.walk("VEVENT"))


def by_summary(calendar):
    return {str(component["SUMMARY"]): component for component in vevents(calendar)}


# Token lifecycle


@pytest.mark.django_db
def test_requires_authentication(api_client):
    assert api_client.get(URL).status_code == 401
    assert api_client.post(URL).status_code == 401


@pytest.mark.django_db
def test_no_feed_by_default(auth_client):
    assert auth_client.get(URL).json() == {"url": None, "include_tasks": False}


@pytest.mark.django_db
def test_create_rotate_and_revoke(auth_client, api_client, settings):
    settings.PUBLIC_URL = "https://librete.example"
    created = enable_feed(auth_client)
    assert created["include_tasks"] is False
    assert created["url"].startswith("https://librete.example/ics/")
    assert created["url"].endswith(".ics")
    assert auth_client.get(URL).json() == created
    assert fetch(api_client, created["url"]).status_code == 200

    rotated = enable_feed(auth_client, include_tasks=True)
    assert rotated["url"] != created["url"]
    assert rotated["include_tasks"] is True
    assert fetch(api_client, created["url"]).status_code == 404
    assert fetch(api_client, rotated["url"]).status_code == 200

    assert auth_client.delete(URL).status_code == 204
    assert auth_client.get(URL).json() == {"url": None, "include_tasks": True}
    assert fetch(api_client, rotated["url"]).status_code == 404


@pytest.mark.django_db
def test_patch_changes_include_tasks_only(auth_client):
    created = enable_feed(auth_client)
    response = auth_client.patch(URL, {"include_tasks": True})
    assert response.status_code == 200
    assert response.json() == {"url": created["url"], "include_tasks": True}
    # Also without a feed (the setting is kept for the next one).
    auth_client.delete(URL)
    assert auth_client.patch(URL, {"include_tasks": False}).json() == {
        "url": None,
        "include_tasks": False,
    }
    assert auth_client.patch(URL, {"include_tasks": "maybe"}).status_code == 400


@pytest.mark.django_db
def test_unknown_tokens_and_deactivated_users(api_client, auth_client, user):
    assert api_client.get("/ics/" + "x" * 43 + ".ics").status_code == 404
    assert api_client.get("/ics/short.ics").status_code == 404
    url = enable_feed(auth_client)["url"]
    user.is_active = False
    user.save()
    assert fetch(api_client, url).status_code == 404


# Contents


@pytest.fixture
def sofia_user(user):
    user.time_zone = "Europe/Sofia"
    user.save()
    return user


@pytest.mark.django_db
def test_feed_headers(api_client, auth_client):
    response = fetch(api_client, enable_feed(auth_client)["url"], HTTP_ACCEPT="text/calendar")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar; charset=utf-8"
    assert response["Cache-Control"] == "private, max-age=300"
    assert response["ETag"].startswith('"')
    calendar = parse(response)
    assert str(calendar["X-WR-CALNAME"]) == "Librete"
    assert str(calendar["VERSION"]) == "2.0"
    assert str(calendar["PRODID"]) == "-//Librete//Librete//EN"


@pytest.mark.django_db
def test_events_series_overrides_and_alarms(api_client, auth_client, sofia_user, settings):
    settings.PUBLIC_DOMAIN = "librete.example"
    plain = EventFactory(
        author=sofia_user,
        name="Dentist",
        start_date=utc(2030, 3, 5, 13, 0),
        end_date=utc(2030, 3, 5, 14, 0),
        location="Clinic",
        reminders=[60, 15],
    )
    series = EventFactory(
        author=sofia_user,
        name="Standup",
        start_date=utc(2030, 3, 4, 7, 0),  # 09:00 EET
        end_date=utc(2030, 3, 4, 7, 30),
        recurrence="FREQ=WEEKLY;BYDAY=MO;COUNT=6",
        exdates=["2030-03-11T07:00:00Z"],
        reminders=[0],
    )
    override = EventFactory(
        author=sofia_user,
        category=series.category,
        name="Standup (moved)",
        recurrence_parent=series,
        original_start=utc(2030, 3, 18, 7, 0),
        start_date=utc(2030, 3, 18, 8, 0),
        end_date=utc(2030, 3, 18, 8, 30),
        reminders=[],
    )
    EventFactory(author=sofia_user, name="Imported", ics_uid="abc@google.com")
    EventFactory(name="Someone else's")

    calendar = parse(fetch(api_client, enable_feed(auth_client)["url"]))
    events = by_summary(calendar)
    assert set(events) == {"Dentist", "Standup", "Standup (moved)", "Imported"}

    dentist = events["Dentist"]
    assert str(dentist["UID"]) == f"librete-event-{plain.id}@librete.example"
    assert dentist["DTSTART"].dt == datetime(2030, 3, 5, 15, 0, tzinfo=SOFIA)
    assert dentist["DTSTART"].params["TZID"] == "Europe/Sofia"
    assert dentist["DTEND"].dt == datetime(2030, 3, 5, 16, 0, tzinfo=SOFIA)
    assert str(dentist["LOCATION"]) == "Clinic"
    assert dentist["CATEGORIES"].cats == [plain.category.name]
    assert str(dentist["URL"]).endswith(f"/events/{plain.id}")
    triggers = [alarm["TRIGGER"].dt for alarm in dentist.walk("VALARM")]
    assert triggers == [timedelta(minutes=-60), timedelta(minutes=-15)]
    assert {str(alarm["ACTION"]) for alarm in dentist.walk("VALARM")} == {"DISPLAY"}

    standup = events["Standup"]
    uid = f"librete-event-{series.id}@librete.example"
    assert str(standup["UID"]) == uid
    assert standup["RRULE"].to_ical() == b"FREQ=WEEKLY;COUNT=6;BYDAY=MO"
    assert standup["DTSTART"].dt == datetime(2030, 3, 4, 9, 0, tzinfo=SOFIA)
    assert [value.dt for value in standup["EXDATE"].dts] == [
        datetime(2030, 3, 11, 9, 0, tzinfo=SOFIA)
    ]
    assert [alarm["TRIGGER"].dt for alarm in standup.walk("VALARM")] == [timedelta(0)]
    assert "RECURRENCE-ID" not in standup

    moved = events["Standup (moved)"]
    assert str(moved["UID"]) == uid
    assert moved["RECURRENCE-ID"].dt == datetime(2030, 3, 18, 9, 0, tzinfo=SOFIA)
    assert moved["DTSTART"].dt == datetime(2030, 3, 18, 10, 0, tzinfo=SOFIA)
    assert str(moved["URL"]).endswith(f"/events/{override.id}")
    assert moved.walk("VALARM") == []

    assert str(events["Imported"]["UID"]) == "abc@google.com"

    # A VTIMEZONE for the TZID is included.
    assert [str(tz["TZID"]) for tz in calendar.walk("VTIMEZONE")] == ["Europe/Sofia"]


@pytest.mark.django_db
def test_series_expands_like_librete(api_client, auth_client, sofia_user):
    """A client expanding the RRULE from the feed gets Librete's occurrences (DST kept)."""
    series = EventFactory(
        author=sofia_user,
        name="Evening",
        start_date=utc(2030, 3, 20, 16, 0),  # 18:00 EET; summer time starts on 31 March
        end_date=utc(2030, 3, 20, 17, 0),
        recurrence="FREQ=WEEKLY;BYDAY=WE;UNTIL=20300430T000000Z",
        exdates=["2030-04-03T15:00:00Z"],
    )
    component = by_summary(parse(fetch(api_client, enable_feed(auth_client)["url"])))["Evening"]
    rule = rrule.rrulestr(component["RRULE"].to_ical().decode(), dtstart=component["DTSTART"].dt)
    excluded = {value.dt for value in component["EXDATE"].dts}
    client_starts = [start.astimezone(UTC) for start in rule if start not in excluded]

    response = auth_client.get(
        "/api/events/",
        {
            "expand": 1,
            "end_date__gte": "2030-03-01T00:00:00Z",
            "start_date__lte": "2030-05-01T00:00:00Z",
        },
    )
    api_starts = [
        datetime.fromisoformat(item["start_date"])
        for item in response.json()["results"]
        if item["id"] == series.id
    ]
    assert client_starts == api_starts
    assert api_starts[-1] == utc(2030, 4, 24, 15, 0)  # still 18:00 local, in summer time


@pytest.mark.django_db
def test_all_day_events(api_client, auth_client, sofia_user):
    # 00:00-23:59 local, as imported all-day events are stored.
    EventFactory(
        author=sofia_user,
        name="Holiday",
        start_date=utc(2030, 3, 2, 22, 0),
        end_date=utc(2030, 3, 4, 21, 59),
        reminders=[],
    )
    series = EventFactory(
        author=sofia_user,
        name="Birthday",
        start_date=utc(2030, 5, 9, 21, 0),
        end_date=utc(2030, 5, 10, 20, 59),
        recurrence="FREQ=YEARLY;UNTIL=20340510T000000Z",
        exdates=["2031-05-09T21:00:00Z"],
    )
    EventFactory(
        author=sofia_user,
        category=series.category,
        name="Birthday party",
        recurrence_parent=series,
        original_start=utc(2032, 5, 9, 21, 0),
        start_date=utc(2032, 5, 10, 15, 0),
        end_date=utc(2032, 5, 10, 18, 0),
    )
    events = by_summary(parse(fetch(api_client, enable_feed(auth_client)["url"])))

    holiday = events["Holiday"]
    assert holiday["DTSTART"].dt == date(2030, 3, 3)
    assert holiday["DTEND"].dt == date(2030, 3, 5)  # exclusive
    birthday = events["Birthday"]
    assert birthday["DTSTART"].dt == date(2030, 5, 10)
    assert birthday["DTEND"].dt == date(2030, 5, 11)
    assert birthday["RRULE"].to_ical() == b"FREQ=YEARLY;UNTIL=20340510"
    assert [value.dt for value in birthday["EXDATE"].dts] == [date(2031, 5, 10)]
    party = events["Birthday party"]
    assert party["RECURRENCE-ID"].dt == date(2032, 5, 10)
    assert party["DTSTART"].dt == datetime(2032, 5, 10, 18, 0, tzinfo=SOFIA)


@pytest.mark.django_db
def test_utc_users_get_utc_times(api_client, auth_client, user):
    EventFactory(author=user, name="Call", start_date=utc(2030, 1, 1, 10), recurrence="FREQ=DAILY")
    response = fetch(api_client, enable_feed(auth_client)["url"])
    assert b"DTSTART:20300101T100000Z" in response.content
    assert parse(response).walk("VTIMEZONE") == []


@pytest.mark.django_db
def test_override_of_a_series_that_stopped_repeating(api_client, auth_client, user):
    series = EventFactory(author=user, start_date=utc(2030, 1, 1, 10), recurrence="FREQ=DAILY")
    override = EventFactory(
        author=user,
        category=series.category,
        name="Override",
        recurrence_parent=series,
        original_start=utc(2030, 1, 2, 10),
    )
    series.recurrence = None
    series.save()
    events = by_summary(parse(fetch(api_client, enable_feed(auth_client)["url"])))
    assert "RECURRENCE-ID" not in events["Override"]
    assert str(events["Override"]["UID"]).startswith(f"librete-event-{override.id}@")


@pytest.mark.django_db
def test_tasks_only_when_enabled(api_client, auth_client, sofia_user, settings):
    settings.PUBLIC_DOMAIN = "librete.example"
    category = CategoryFactory(author=sofia_user, name="Home")
    due = TaskFactory(
        author=sofia_user,
        category=category,
        name="Pay rent",
        end_date=utc(2030, 3, 5, 10, 0),
        reminders=[30],
    )
    ranged = TaskFactory(
        author=sofia_user,
        category=category,
        name="Paint",
        start_date=utc(2030, 3, 6, 7, 0),
        end_date=utc(2030, 3, 6, 15, 0),
        reminders=[60],
    )
    TaskFactory(
        author=sofia_user,
        category=category,
        name="Whole day",
        start_date=utc(2030, 3, 6, 22, 0),  # 00:00 local
        reminders=[],
    )
    TaskFactory(
        author=sofia_user,
        category=category,
        name="Done",
        end_date=utc(2030, 3, 1, 10, 0),
        status=Task.Status.FINISHED,
        reminders=[30],
    )
    TaskFactory(author=sofia_user, category=category, name="Someday")
    TaskFactory(name="Theirs", end_date=utc(2030, 3, 5, 10, 0))

    url = enable_feed(auth_client)["url"]
    assert vevents(parse(fetch(api_client, url))) == []

    auth_client.patch(URL, {"include_tasks": True})
    events = by_summary(parse(fetch(api_client, url)))
    assert set(events) == {"Pay rent", "Paint", "Whole day", "✓ Done"}

    rent = events["Pay rent"]
    assert str(rent["UID"]) == f"librete-task-{due.id}@librete.example"
    assert rent["DTSTART"].dt == datetime(2030, 3, 5, 12, 0, tzinfo=SOFIA)
    assert "DTEND" not in rent
    assert [alarm["TRIGGER"].dt for alarm in rent.walk("VALARM")] == [timedelta(minutes=-30)]
    assert str(rent["URL"]).endswith(f"/tasks/{due.id}")

    paint = events["Paint"]
    assert str(paint["UID"]) == f"librete-task-{ranged.id}@librete.example"
    assert paint["DTEND"].dt == datetime(2030, 3, 6, 17, 0, tzinfo=SOFIA)
    # 60 minutes before the due date (the end), relative to the start.
    assert [alarm["TRIGGER"].dt for alarm in paint.walk("VALARM")] == [timedelta(hours=7)]

    assert events["Whole day"]["DTSTART"].dt == date(2030, 3, 7)
    assert events["Whole day"]["DTEND"].dt == date(2030, 3, 8)
    assert events["✓ Done"].walk("VALARM") == []


# Caching and throttling


@pytest.mark.django_db
def test_etag_and_not_modified(api_client, auth_client, user):
    EventFactory(author=user, name="First")
    url = enable_feed(auth_client)["url"]
    first = fetch(api_client, url)
    etag = first["ETag"]

    not_modified = fetch(api_client, url, HTTP_IF_NONE_MATCH=etag)
    assert not_modified.status_code == 304
    assert not_modified.content == b""
    assert not_modified["ETag"] == etag
    assert fetch(api_client, url, HTTP_IF_NONE_MATCH=f'"other", W/{etag}').status_code == 304
    assert fetch(api_client, url, HTTP_IF_NONE_MATCH='"other"').status_code == 200


@pytest.mark.django_db
def test_feed_is_cached_for_five_minutes(api_client, auth_client, user):
    with time_machine.travel(utc(2030, 1, 1, 12, 0), tick=False) as traveller:
        EventFactory(author=user, name="First")
        url = enable_feed(auth_client)["url"]
        first = fetch(api_client, url)
        EventFactory(author=user, name="Second")

        traveller.shift(timedelta(minutes=4))
        cached = fetch(api_client, url)
        assert cached.content == first.content
        assert cached["ETag"] == first["ETag"]

        traveller.shift(timedelta(minutes=2))
        fresh = fetch(api_client, url)
        assert fresh["ETag"] != first["ETag"]
        assert set(by_summary(parse(fresh))) == {"First", "Second"}
        assert fetch(api_client, url, HTTP_IF_NONE_MATCH=first["ETag"]).status_code == 200


@pytest.mark.django_db
def test_feed_output_is_stable(api_client, auth_client, user):
    EventFactory(author=user, reminders=[10], recurrence="FREQ=DAILY;COUNT=3")
    url = enable_feed(auth_client)["url"]
    first = fetch(api_client, url)
    cache.clear()
    assert fetch(api_client, url)["ETag"] == first["ETag"]


@pytest.mark.django_db
def test_feed_is_throttled_per_token(api_client, auth_client, client_for, other_user, monkeypatch):
    rates = {**FeedTokenThrottle.THROTTLE_RATES, "ics_feed": "2/hour"}
    monkeypatch.setattr(FeedTokenThrottle, "THROTTLE_RATES", rates)
    url = enable_feed(auth_client)["url"]
    assert fetch(api_client, url).status_code == 200
    assert fetch(api_client, url).status_code == 200
    assert fetch(api_client, url).status_code == 429
    # Another feed URL has its own limit.
    other = client_for(other_user)
    assert fetch(api_client, enable_feed(other)["url"]).status_code == 200
