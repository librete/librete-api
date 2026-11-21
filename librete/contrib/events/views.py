from datetime import timedelta

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters import utils as filter_utils
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from librete.utils.recurrence import zone
from librete.utils.viewsets import OwnedModelViewSet

from .models import Event
from .recurrence import occurrence_instance, occurrences, overridden_starts
from .serializers import EventSerializer

MAX_EXPAND_RANGE = timedelta(days=400)
DATE_FILTERS = ("start_date__lte", "start_date__gte", "end_date__lte", "end_date__gte")


class ExpandQuerySerializer(serializers.Serializer):
    expand = serializers.BooleanField(required=False, default=False)
    start_date__lte = serializers.DateTimeField(required=False)
    start_date__gte = serializers.DateTimeField(required=False)
    end_date__lte = serializers.DateTimeField(required=False)
    end_date__gte = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if not attrs["expand"]:
            return attrs
        missing = {
            name: [_("Required with expand=1.")]
            for name in ("start_date__lte", "end_date__gte")
            if name not in attrs
        }
        if missing:
            raise serializers.ValidationError(missing)
        if attrs["start_date__lte"] - attrs["end_date__gte"] > MAX_EXPAND_RANGE:
            raise serializers.ValidationError(
                {
                    "expand": [
                        _("The range can be at most %(days)s days.")
                        % {"days": MAX_EXPAND_RANGE.days}
                    ]
                }
            )
        return attrs


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "expand",
                OpenApiTypes.BOOL,
                description="`1`: return the occurrences of recurring events in the range "
                "`end_date__gte`..`start_date__lte` (both required, at most "
                f"{MAX_EXPAND_RANGE.days} days) instead of the series, ordered by "
                "`start_date`. Occurrences carry the series `id`, their own "
                "`start_date`/`end_date`, `occurrence_start` and `is_occurrence: true`; "
                "skipped (`exdates`) and overridden occurrences are left out, and overrides "
                "are listed as stored events with `occurrence_start` = their "
                "`original_start`. `category` and `search` still apply; `ordering` doesn't.",
            ),
            OpenApiParameter(
                "repeating",
                OpenApiTypes.BOOL,
                description="`1`: only series (events with `recurrence`) and their overrides "
                "(events with `recurrence_parent`), stored rows. The app keeps these on the "
                "device and expands them itself.",
            ),
        ]
    )
)
class EventViewSet(OwnedModelViewSet):
    model = Event
    serializer_class = EventSerializer
    filterset_fields = {
        "category": ["exact"],
        "start_date": ["gte", "lte"],
        "end_date": ["gte", "lte"],
    }
    search_fields = ("name", "location", "description")
    ordering_fields = ("name", "start_date", "end_date", "created_at", "updated_at")

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.request.query_params.get("repeating", "").lower() in ("1", "true"):
            queryset = queryset.filter(
                Q(recurrence__isnull=False) | Q(recurrence_parent__isnull=False)
            )
        return queryset

    def list(self, request, *args, **kwargs):
        if "expand" not in request.query_params:
            return super().list(request, *args, **kwargs)
        query = ExpandQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        if not query.validated_data["expand"]:
            return super().list(request, *args, **kwargs)

        items = self._expanded(query.validated_data)
        page = self.paginate_queryset(items)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(items, many=True).data)

    def _filter_series(self, queryset):
        """Apply the list filters except the date bounds (they apply to occurrences)."""
        data = self.request.query_params.copy()
        for name in DATE_FILTERS:
            data.pop(name, None)
        filterset_class = DjangoFilterBackend().get_filterset_class(self, queryset)
        filterset = filterset_class(data, queryset=queryset, request=self.request)
        if not filterset.is_valid():
            raise filter_utils.translate_validation(filterset.errors)
        return SearchFilter().filter_queryset(self.request, filterset.qs, self)

    def _expanded(self, params):
        range_start, range_end = params["end_date__gte"], params["start_date__lte"]
        start_from, end_until = params.get("start_date__gte"), params.get("end_date__lte")

        # Non-recurring events and overrides: stored rows filtered as usual.
        items = list(self.filter_queryset(self.get_queryset()).filter(recurrence__isnull=True))
        for item in items:
            if item.recurrence_parent_id is not None:
                item.occurrence_start = item.original_start

        series = list(
            self._filter_series(self.get_queryset()).filter(
                recurrence__isnull=False, start_date__lte=range_end
            )
        )
        if series:
            overrides = Event.objects.filter(
                author=self.request.user, recurrence_parent__in=[s.pk for s in series]
            ).only("recurrence_parent_id", "original_start")
            skip = overridden_starts(overrides)
            tz = zone(self.request.user.time_zone)
            for item in series:
                for start, end in occurrences(
                    item, tz, range_start, range_end, skip.get(item.pk, ())
                ):
                    if (start_from and start < start_from) or (end_until and end > end_until):
                        continue
                    items.append(occurrence_instance(item, start, end))

        items.sort(key=lambda item: (item.start_date, item.pk))
        return items
