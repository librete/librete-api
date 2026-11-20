from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from librete.tests.factories import EventFactory, NoteFactory, TaskFactory

UTC = ZoneInfo("UTC")


@pytest.mark.django_db
def test_stats(auth_client, user, other_user):
    EventFactory(
        author=user,
        start_date=datetime(2030, 1, 15, tzinfo=UTC),
        end_date=datetime(2030, 1, 16, tzinfo=UTC),
    )
    EventFactory(
        author=user,
        start_date=datetime(2030, 3, 1, tzinfo=UTC),
        end_date=datetime(2030, 3, 2, tzinfo=UTC),
    )
    EventFactory(
        author=user,
        start_date=datetime(2031, 3, 1, tzinfo=UTC),
        end_date=datetime(2031, 3, 2, tzinfo=UTC),
    )
    TaskFactory(author=user, start_date=datetime(2030, 12, 31, tzinfo=UTC), status="finished")
    EventFactory(
        author=other_user,
        start_date=datetime(2030, 1, 15, tzinfo=UTC),
        end_date=datetime(2030, 1, 16, tzinfo=UTC),
    )

    response = auth_client.get("/api/stats/?year=2030")
    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2030
    assert body["totals"] == {
        "categories": 4,
        "events": 3,
        "notes": 0,
        "tasks": 1,
        "active_tasks": 0,
    }
    assert body["monthly"]["events"] == [1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    assert body["monthly"]["tasks"][11] == 1


@pytest.mark.django_db
def test_stats_respect_time_zone(auth_client, user):
    # 23:30 UTC on 31 Jan is already 1 Feb in Sofia (UTC+2).
    EventFactory(
        author=user,
        start_date=datetime(2030, 1, 31, 23, 30, tzinfo=UTC),
        end_date=datetime(2030, 2, 1, 23, 30, tzinfo=UTC),
    )
    utc = auth_client.get("/api/stats/?year=2030").json()["monthly"]["events"]
    sofia = auth_client.get("/api/stats/?year=2030&tz=Europe/Sofia").json()["monthly"]["events"]
    assert utc[:2] == [1, 0]
    assert sofia[:2] == [0, 1]


@pytest.mark.django_db
def test_notes_and_tasks_without_dates_use_creation_date(auth_client, user):
    NoteFactory(author=user)
    TaskFactory(author=user, start_date=None)
    body = auth_client.get("/api/stats/").json()
    assert sum(body["monthly"]["notes"]) == 1
    assert sum(body["monthly"]["tasks"]) == 1


@pytest.mark.django_db
def test_invalid_parameters(auth_client):
    assert auth_client.get("/api/stats/?tz=Mars/Base").status_code == 400
    assert auth_client.get("/api/stats/?year=abc").status_code == 400
