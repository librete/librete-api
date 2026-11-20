from django.db import connection
from django.db.models import Case, F, FloatField, Q, Value, When
from django.db.models.functions import Greatest
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    PolymorphicProxySerializer,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from librete.contrib.sync.resources import RESOURCES

# Fields searched per type (each has a GIN trigram index on PostgreSQL, see migration 0001).
SEARCH_FIELDS = {
    "events": ("name", "location", "description"),
    "notes": ("name", "text"),
    "tasks": ("name", "description"),
    "categories": ("name", "description"),
}
TYPES = tuple(SEARCH_FIELDS)
# Types limited by the `category` parameter.
CATEGORIZED = ("events", "notes", "tasks")

MIN_QUERY_LENGTH = 2
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
# A row matches when its trigram score reaches this, or when a field contains the query.
THRESHOLD = 0.3
# The score of a row that contains the query, if its trigram score is lower.
CONTAINS_SCORE = 0.5


class SearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField()
    types = serializers.CharField(required=False, allow_blank=True)
    category = serializers.IntegerField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, default=DEFAULT_LIMIT)

    def validate_q(self, value):
        if len(value) < MIN_QUERY_LENGTH:
            raise serializers.ValidationError(
                _("Enter at least %(min)s characters.") % {"min": MIN_QUERY_LENGTH}
            )
        return value

    def validate_types(self, value):
        types = [item.strip() for item in value.split(",") if item.strip()]
        unknown = sorted(set(types) - set(TYPES))
        if unknown:
            raise serializers.ValidationError(
                _("Unknown types: %(types)s.") % {"types": ", ".join(unknown)}
            )
        return [type for type in TYPES if type in types]

    def validate_limit(self, limit):
        return min(limit, MAX_LIMIT)


def _contains(fields, query):
    condition = Q()
    for field in fields:
        condition |= Q(**{f"{field}__icontains": query})
    return condition


def _search(queryset, fields, query):
    """Annotate `score` and keep the matching rows (see the contract in SearchView)."""
    contains = _contains(fields, query)
    if connection.vendor != "postgresql":
        return queryset.filter(contains).annotate(score=Value(1.0, output_field=FloatField()))

    from django.contrib.postgres.search import TrigramSimilarity, TrigramWordSimilarity

    scores = []
    for field in fields:
        scores.append(TrigramSimilarity(field, query))
        scores.append(TrigramWordSimilarity(query, field))
    scores.append(
        Case(
            When(contains, then=Value(CONTAINS_SCORE)),
            default=Value(0.0),
            output_field=FloatField(),
        )
    )
    score = Greatest(*scores, output_field=FloatField())
    return queryset.annotate(score=score).filter(Q(score__gte=THRESHOLD) | contains)


RESULT_SCHEMA = inline_serializer(
    "SearchResult",
    {
        "type": serializers.ChoiceField(choices=TYPES),
        "id": serializers.IntegerField(),
        "score": serializers.FloatField(help_text="0..1, higher is a better match."),
        "item": PolymorphicProxySerializer(
            component_name="SearchItem",
            serializers=[RESOURCES[type].serializer_class for type in TYPES],
            resource_type_field_name=None,
            many=False,
            help_text="The item exactly as `GET /api/<type>/<id>/` returns it.",
        ),
    },
    many=True,
)


class SearchView(APIView):
    """Search the user's events, notes, tasks and categories.

    On PostgreSQL rows are ranked by trigram similarity (typo-tolerant, works for any
    script): the score is the greatest `similarity` / `word_similarity` between the query
    and the searched fields, and a row matches when it reaches 0.3 or a field contains the
    query (case-insensitive; such rows score at least 0.5). Elsewhere (SQLite in
    development) only containment is checked and every score is 1.0. `results` merges all
    types, best first (then most recently updated); `counts` are the matches per requested
    type before `limit`.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "q",
                OpenApiTypes.STR,
                required=True,
                description=f"Search text, at least {MIN_QUERY_LENGTH} characters after trimming.",
            ),
            OpenApiParameter(
                "types",
                OpenApiTypes.STR,
                description="Comma-separated subset of `events,notes,tasks,categories` "
                "(default: all).",
            ),
            OpenApiParameter(
                "category",
                OpenApiTypes.INT,
                description="Limit events, notes and tasks to this category.",
            ),
            OpenApiParameter(
                "limit",
                OpenApiTypes.INT,
                description=f"Results per type, default {DEFAULT_LIMIT}, max {MAX_LIMIT}.",
            ),
        ],
        responses=inline_serializer(
            "Search",
            {
                "query": serializers.CharField(help_text="The trimmed query."),
                "results": RESULT_SCHEMA,
                "counts": serializers.DictField(
                    child=serializers.IntegerField(),
                    help_text="Matches per requested type, before `limit`.",
                ),
            },
        ),
    )
    def get(self, request):
        params = SearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        query = params.validated_data["q"]
        types = params.validated_data.get("types") or list(TYPES)
        category = params.validated_data.get("category")
        limit = params.validated_data["limit"]

        results, counts = [], {}
        for type in types:
            resource = RESOURCES[type]
            queryset = resource.queryset(request.user)
            if category is not None and type in CATEGORIZED:
                queryset = queryset.filter(category_id=category)
            matches = _search(queryset, SEARCH_FIELDS[type], query)
            counts[type] = matches.count()
            rows = list(matches.order_by(F("score").desc(), "-updated_at", "-pk")[:limit])
            serialized = resource.serializer_class(
                rows, many=True, context={"request": request}
            ).data
            for row, item in zip(rows, serialized, strict=True):
                results.append(
                    {
                        "type": type,
                        "id": row.pk,
                        "score": round(float(row.score), 4),
                        "item": item,
                        "_sort": (-row.score, -row.updated_at.timestamp()),
                    }
                )

        results.sort(key=lambda result: result["_sort"])
        for result in results:
            del result["_sort"]
        return Response({"query": query, "results": results, "counts": counts})
