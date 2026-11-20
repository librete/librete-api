import zoneinfo

from django.db.models import Count, F
from django.db.models.functions import Coalesce, ExtractMonth
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from librete.contrib.categories.models import Category
from librete.contrib.events.models import Event
from librete.contrib.notes.models import Note
from librete.contrib.tasks.models import Task


def _monthly(queryset, field, year):
    counts = dict(
        queryset.annotate(_date=field)
        .filter(_date__year=year)
        .annotate(month=ExtractMonth("_date"))
        .order_by()
        .values("month")
        .annotate(count=Count("pk"))
        .values_list("month", "count")
    )
    return [counts.get(month, 0) for month in range(1, 13)]


class StatsView(APIView):
    """Totals and per-month activity for the home screen.

    Events are counted by start date, notes by creation date and tasks by start date
    (creation date for tasks without one), in the time zone given by `tz`.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter("year", OpenApiTypes.INT, description="Defaults to this year."),
            OpenApiParameter("tz", OpenApiTypes.STR, description="IANA zone, default UTC."),
        ],
        responses=inline_serializer(
            "Stats",
            {
                "year": serializers.IntegerField(),
                "totals": serializers.DictField(child=serializers.IntegerField()),
                "monthly": serializers.DictField(
                    child=serializers.ListField(child=serializers.IntegerField())
                ),
            },
        ),
    )
    def get(self, request):
        try:
            tz = zoneinfo.ZoneInfo(request.query_params.get("tz") or "UTC")
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as error:
            raise serializers.ValidationError({"tz": "Unknown time zone."}) from error

        with timezone.override(tz):
            try:
                year = int(request.query_params.get("year") or timezone.localdate().year)
            except ValueError as error:
                raise serializers.ValidationError({"year": "A valid year is required."}) from error

            user = request.user
            events = Event.objects.filter(author=user)
            notes = Note.objects.filter(author=user)
            tasks = Task.objects.filter(author=user)

            data = {
                "year": year,
                "totals": {
                    "categories": Category.objects.filter(author=user).count(),
                    "events": events.count(),
                    "notes": notes.count(),
                    "tasks": tasks.count(),
                    "active_tasks": tasks.filter(status=Task.Status.ACTIVE).count(),
                },
                "monthly": {
                    "events": _monthly(events, F("start_date"), year),
                    "notes": _monthly(notes, F("created_at"), year),
                    "tasks": _monthly(tasks, Coalesce("start_date", "created_at"), year),
                },
            }
        return Response(data)
