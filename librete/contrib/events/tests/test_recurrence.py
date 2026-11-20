import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from librete.contrib.events.models import Event
from librete.contrib.sync.models import Change
from librete.tests.factories import CategoryFactory, EventFactory, UserFactory

VECTORS = json.loads((Path(__file__).parent / "rrule_vectors.json").read_text())
START = datetime(2030, 5, 1, 9, 0, tzinfo=UTC)


def iso(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture
def category(user):
    return CategoryFactory(author=user)


def payload(category, **overrides):
    data = {
        "name": "Standup",
        "category": category.id,
        "start_date": "2030-05-01T09:00:00Z",
        "end_date": "2030-05-01T09:15:00Z",
    }
    data.update(overrides)
    return data


def expand(client, range_start, range_end, **params):
    response = client.get(
        "/api/events/",
        {
            "expand": "1",
            "end_date__gte": range_start,
            "start_date__lte": range_end,
            "page_size": 100,
            **params,
        },
    )
    assert response.status_code == 200, response.json()
    return response.json()


def series(author, rule="FREQ=DAILY", **kwargs):
    kwargs.setdefault("start_date", START)
    kwargs.setdefault("end_date", kwargs["start_date"] + timedelta(hours=1))
    return EventFactory(author=author, recurrence=rule, reminders=[], **kwargs)


# Validation


@pytest.mark.django_db
def test_create_series_returns_the_new_fields(auth_client, category):
    response = auth_client.post(
        "/api/events/",
        payload(
            category,
            recurrence=" freq=weekly;byday=mo,we;interval=2 ",
            exdates=[
                "2030-05-06T12:00:00+03:00",
                "2030-05-06T09:00:00Z",
                "2030-05-08T09:00:00.5Z",
            ],
        ),
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["recurrence"] == "FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2"
    assert body["exdates"] == ["2030-05-06T09:00:00Z", "2030-05-08T09:00:00Z"]
    assert body["recurrence_parent"] is None
    assert body["original_start"] is None
    assert body["occurrence_start"] is None
    assert body["is_occurrence"] is False


@pytest.mark.django_db
def test_defaults_for_plain_events(auth_client, category):
    body = auth_client.post("/api/events/", payload(category)).json()
    assert body["recurrence"] is None
    assert body["exdates"] == []
    assert (
        auth_client.patch(f"/api/events/{body['id']}/", {"recurrence": ""}).json()["recurrence"]
        is None
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "rule",
    [
        "RRULE:FREQ=DAILY",
        "FREQ=HOURLY",
        "FREQ=MINUTELY",
        "FREQ=DAILY;BYHOUR=9,17",
        "INTERVAL=2",
        "FREQ=DAILY;COUNT=0",
        "FREQ=DAILY;INTERVAL=0",
        "FREQ=WEEKLY;BYDAY=XX",
        "FREQ=MONTHLY;BYMONTHDAY=32",
        "FREQ=YEARLY;BYMONTH=13",
        "FREQ=DAILY;COUNT=3;UNTIL=20300601T000000Z",
        "FREQ=DAILY;UNTIL=20300601",
        "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30",
        "FREQ=DAILY\nDTSTART:20300101T000000Z",
        "FREQ=DAILY;X-NAME=1",
        "FREQ=DAILY;" + "BYMONTHDAY=1;" * 60,
    ],
)
def test_invalid_recurrence(auth_client, category, rule):
    response = auth_client.post("/api/events/", payload(category, recurrence=rule))
    assert response.status_code == 400
    assert "recurrence" in response.json()
    assert not Event.objects.exists()


@pytest.mark.django_db
def test_a_rule_that_already_ended_is_allowed(auth_client, category):
    # "This and following" from the first occurrence leaves the old series without any.
    response = auth_client.post(
        "/api/events/", payload(category, recurrence="FREQ=DAILY;UNTIL=20300430T000000Z")
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_invalid_exdates(auth_client, category):
    response = auth_client.post(
        "/api/events/", payload(category, recurrence="FREQ=DAILY", exdates=["tomorrow"])
    )
    assert response.status_code == 400
    assert "exdates" in response.json()


@pytest.mark.django_db
def test_override_validation(auth_client, user, other_user, category):
    parent = series(user, category=category)
    plain = EventFactory(author=user, category=category)
    foreign = series(other_user)
    occurrence = "2030-05-02T09:00:00Z"

    def post(**fields):
        return auth_client.post("/api/events/", payload(category, **fields))

    response = post(recurrence_parent=parent.id, original_start=occurrence)
    assert response.status_code == 201, response.json()
    assert response.json()["recurrence_parent"] == parent.id
    assert response.json()["original_start"] == occurrence

    assert "original_start" in post(recurrence_parent=parent.id).json()
    assert "original_start" in post(original_start=occurrence).json()
    assert (
        "recurrence"
        in post(
            recurrence_parent=parent.id, original_start=occurrence, recurrence="FREQ=DAILY"
        ).json()
    )
    assert (
        "recurrence_parent" in post(recurrence_parent=plain.id, original_start=occurrence).json()
    )
    assert (
        "recurrence_parent" in post(recurrence_parent=foreign.id, original_start=occurrence).json()
    )
    override_id = response.json()["id"]
    assert (
        "recurrence_parent"
        in post(recurrence_parent=override_id, original_start=occurrence).json()
    )
    response = auth_client.patch(f"/api/events/{override_id}/", {"recurrence": "FREQ=DAILY"})
    assert response.status_code == 400
    assert "recurrence" in response.json()


@pytest.mark.django_db
def test_changing_the_start_revalidates_the_rule(auth_client, user, category):
    event = series(user, rule="FREQ=YEARLY;BYMONTH=5;BYMONTHDAY=1", category=category)
    url = f"/api/events/{event.id}/"
    assert auth_client.patch(url, {"name": "Renamed"}).status_code == 200
    response = auth_client.patch(
        url, {"start_date": "2030-06-01T09:00:00Z", "end_date": "2030-06-01T10:00:00Z"}
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_deleting_a_series_deletes_its_overrides_and_logs_them(user, category):
    parent = series(user, category=category)
    override = EventFactory(
        author=user,
        category=category,
        recurrence_parent=parent,
        original_start=START + timedelta(days=1),
    )
    ids = {parent.pk, override.pk}
    parent.delete()
    assert not Event.objects.exists()
    deleted = Change.objects.filter(user=user, type="events", op="delete")
    assert set(deleted.values_list("object_id", flat=True)) == ids


@pytest.mark.django_db
def test_sync_payload_includes_the_recurrence_fields(auth_client, user, category):
    parent = series(user, category=category, exdates=["2030-05-03T09:00:00Z"])
    override = EventFactory(
        author=user,
        category=category,
        recurrence_parent=parent,
        original_start=START + timedelta(days=1),
    )
    changes = auth_client.get("/api/sync/", {"since": 0, "types": "events"}).json()["changes"]
    data = {change["id"]: change["data"] for change in changes}
    assert data[parent.id]["recurrence"] == "FREQ=DAILY"
    assert data[parent.id]["exdates"] == ["2030-05-03T09:00:00Z"]
    assert data[override.id]["recurrence_parent"] == parent.id
    assert data[override.id]["original_start"] == "2030-05-02T09:00:00Z"
    assert data[override.id]["occurrence_start"] is None
    assert data[override.id]["is_occurrence"] is False
    assert data[parent.id] == auth_client.get(f"/api/events/{parent.id}/").json()


# Expansion


@pytest.mark.django_db
@pytest.mark.parametrize("vector", VECTORS, ids=[vector["name"] for vector in VECTORS])
def test_expansion_matches_the_shared_vectors(client_for, vector):
    user = UserFactory(time_zone=vector["time_zone"])
    event = series(
        user,
        rule=vector["recurrence"],
        start_date=parse(vector["start"]),
        end_date=parse(vector["end"]),
        exdates=vector["exdates"],
    )
    body = expand(client_for(user), vector["range_start"], vector["range_end"])
    assert [item["start_date"] for item in body["results"]] == vector["expected_starts"]
    duration = parse(vector["end"]) - parse(vector["start"])
    for item in body["results"]:
        assert item["id"] == event.id
        assert item["is_occurrence"] is True
        assert item["occurrence_start"] == item["start_date"]
        assert parse(item["end_date"]) - parse(item["start_date"]) == duration


@pytest.mark.django_db
def test_expanded_list_mixes_events_occurrences_and_overrides(auth_client, user, category):
    parent = series(
        user,
        rule="FREQ=DAILY;COUNT=5",
        category=category,
        name="Standup",
        exdates=["2030-05-04T09:00:00Z"],
    )
    moved = EventFactory(
        author=user,
        category=category,
        name="Standup (moved)",
        recurrence_parent=parent,
        original_start=START + timedelta(days=1),
        start_date=START + timedelta(days=1, hours=5),
        end_date=START + timedelta(days=1, hours=6),
    )
    plain = EventFactory(
        author=user,
        category=category,
        start_date=START + timedelta(hours=2),
        end_date=START + timedelta(hours=3),
    )
    EventFactory(author=user, category=category, start_date=START + timedelta(days=30))

    body = expand(auth_client, "2030-05-01T00:00:00Z", "2030-05-31T00:00:00Z")

    rows = [
        (item["id"], item["start_date"], item["occurrence_start"], item["is_occurrence"])
        for item in body["results"]
    ]
    assert rows == [
        (parent.id, "2030-05-01T09:00:00Z", "2030-05-01T09:00:00Z", True),
        (plain.id, "2030-05-01T11:00:00Z", None, False),
        (moved.id, "2030-05-02T14:00:00Z", "2030-05-02T09:00:00Z", False),
        (parent.id, "2030-05-03T09:00:00Z", "2030-05-03T09:00:00Z", True),
        (parent.id, "2030-05-05T09:00:00Z", "2030-05-05T09:00:00Z", True),
    ]
    occurrence = body["results"][0]
    assert occurrence["name"] == "Standup"
    assert occurrence["recurrence"] == "FREQ=DAILY;COUNT=5"
    assert occurrence["end_date"] == "2030-05-01T10:00:00Z"


@pytest.mark.django_db
def test_without_expand_series_and_overrides_are_listed_once(auth_client, user, category):
    parent = series(user, category=category)
    override = EventFactory(
        author=user, category=category, recurrence_parent=parent, original_start=START
    )
    for params in ({}, {"expand": "0"}):
        results = auth_client.get("/api/events/", params).json()["results"]
        assert sorted(item["id"] for item in results) == sorted([parent.id, override.id])
        assert {item["occurrence_start"] for item in results} == {None}
        assert {item["is_occurrence"] for item in results} == {False}


@pytest.mark.django_db
def test_override_in_another_category_still_replaces_the_occurrence(auth_client, user, category):
    parent = series(user, rule="FREQ=DAILY;COUNT=2", category=category)
    elsewhere = CategoryFactory(author=user)
    EventFactory(author=user, category=elsewhere, recurrence_parent=parent, original_start=START)
    body = expand(
        auth_client, "2030-05-01T00:00:00Z", "2030-05-31T00:00:00Z", category=category.id
    )
    assert [item["start_date"] for item in body["results"]] == ["2030-05-02T09:00:00Z"]


@pytest.mark.django_db
def test_category_and_search_filters_apply_to_series(auth_client, user, category):
    other = CategoryFactory(author=user)
    yoga = series(user, rule="FREQ=DAILY;COUNT=2", category=category, name="Yoga")
    series(user, rule="FREQ=DAILY;COUNT=2", category=other, name="Run")
    by_category = expand(
        auth_client, "2030-05-01T00:00:00Z", "2030-05-31T00:00:00Z", category=category.id
    )
    by_search = expand(auth_client, "2030-05-01T00:00:00Z", "2030-05-31T00:00:00Z", search="yog")
    for body in (by_category, by_search):
        assert {item["id"] for item in body["results"]} == {yoga.id}
        assert body["count"] == 2


@pytest.mark.django_db
def test_optional_inner_bounds_apply_to_occurrences(auth_client, user):
    series(user, rule="FREQ=DAILY;COUNT=5")
    body = expand(
        auth_client,
        "2030-05-01T00:00:00Z",
        "2030-05-31T00:00:00Z",
        start_date__gte="2030-05-02T00:00:00Z",
        end_date__lte="2030-05-04T00:00:00Z",
    )
    assert [item["start_date"] for item in body["results"]] == [
        "2030-05-02T09:00:00Z",
        "2030-05-03T09:00:00Z",
    ]


@pytest.mark.django_db
def test_expanded_results_are_paginated_in_start_order(auth_client, user):
    series(user, rule="FREQ=DAILY", name="A")
    series(user, rule="FREQ=DAILY", name="B", start_date=START - timedelta(hours=1))
    first = auth_client.get(
        "/api/events/",
        {
            "expand": "1",
            "end_date__gte": "2030-05-01T00:00:00Z",
            "start_date__lte": "2030-05-20T23:59:59Z",
        },
    ).json()
    assert first["count"] == 40
    assert len(first["results"]) == 25
    second = auth_client.get(first["next"]).json()
    starts = [item["start_date"] for item in first["results"] + second["results"]]
    assert len(starts) == 40
    assert starts == sorted(starts)
    assert starts[:2] == ["2030-05-01T08:00:00Z", "2030-05-01T09:00:00Z"]


@pytest.mark.django_db
def test_other_users_series_are_not_expanded(auth_client, user, other_user):
    series(other_user)
    assert expand(auth_client, "2030-05-01T00:00:00Z", "2030-05-31T00:00:00Z")["count"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"start_date__lte": "2030-05-31T00:00:00Z"}, "end_date__gte"),
        ({"end_date__gte": "2030-05-01T00:00:00Z"}, "start_date__lte"),
        (
            {"end_date__gte": "2030-01-01T00:00:00Z", "start_date__lte": "2031-02-05T00:00:01Z"},
            "expand",
        ),
        (
            {"end_date__gte": "yesterday", "start_date__lte": "2030-05-31T00:00:00Z"},
            "end_date__gte",
        ),
    ],
)
def test_expand_parameter_errors(auth_client, user, params, field):
    response = auth_client.get("/api/events/", {"expand": "1", **params})
    assert response.status_code == 400
    assert field in response.json()


@pytest.mark.django_db
def test_a_range_of_400_days_is_allowed(auth_client, user):
    body = expand(auth_client, "2030-01-01T00:00:00Z", "2031-02-05T00:00:00Z")
    assert body["count"] == 0


@pytest.mark.django_db
def test_expansion_uses_the_authors_current_time_zone(client_for):
    user = UserFactory(time_zone="UTC")
    series(user, rule="FREQ=DAILY;COUNT=3", start_date=datetime(2030, 3, 30, 9, tzinfo=UTC))
    body = expand(client_for(user), "2030-03-30T00:00:00Z", "2030-04-02T00:00:00Z")
    assert [item["start_date"] for item in body["results"]] == [
        "2030-03-30T09:00:00Z",
        "2030-03-31T09:00:00Z",
        "2030-04-01T09:00:00Z",
    ]
    user.time_zone = "Europe/Sofia"
    user.save()
    body = expand(client_for(user), "2030-03-30T00:00:00Z", "2030-04-02T00:00:00Z")
    assert [item["start_date"] for item in body["results"]] == [
        "2030-03-30T09:00:00Z",
        "2030-03-31T08:00:00Z",
        "2030-04-01T08:00:00Z",
    ]


@pytest.mark.django_db
def test_recurrence_errors_are_translated(auth_client, category):
    response = auth_client.post(
        "/api/events/", payload(category, recurrence="FREQ=HOURLY"), HTTP_ACCEPT_LANGUAGE="bg"
    )
    assert response.json()["recurrence"] == [
        "Честотата трябва да бъде DAILY, WEEKLY, MONTHLY или YEARLY."
    ]
