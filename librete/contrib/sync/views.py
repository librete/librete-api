from django.db.models import Max
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

from .models import Change
from .resources import RESOURCES

DEFAULT_LIMIT = 500
MAX_LIMIT = 1000


class SyncQuerySerializer(serializers.Serializer):
    since = serializers.IntegerField(required=False, min_value=0)
    limit = serializers.IntegerField(required=False, min_value=1, default=DEFAULT_LIMIT)
    types = serializers.CharField(required=False, allow_blank=True)

    def validate_limit(self, limit):
        return min(limit, MAX_LIMIT)

    def validate_types(self, value):
        types = [item.strip() for item in value.split(",") if item.strip()]
        unknown = sorted(set(types) - set(RESOURCES))
        if unknown:
            raise serializers.ValidationError(
                _("Unknown types: %(types)s.") % {"types": ", ".join(unknown)}
            )
        return types


CHANGES_SCHEMA = inline_serializer(
    "SyncChange",
    {
        "seq": serializers.IntegerField(help_text="Change id; a later change has a higher one."),
        "type": serializers.ChoiceField(choices=Change.Type.choices),
        "id": serializers.IntegerField(help_text="Id of the changed item."),
        "op": serializers.ChoiceField(choices=Change.Op.choices),
        "data": PolymorphicProxySerializer(
            component_name="SyncItem",
            serializers=[resource.serializer_class for resource in RESOURCES.values()],
            resource_type_field_name=None,
            many=False,
            allow_null=True,
            help_text="For `upsert`: the item exactly as `GET /api/<type>/<id>/` returns it. "
            "`null` for `delete`.",
        ),
    },
    many=True,
)


class SyncView(APIView):
    """Delta sync: what changed in the user's categories, events, notes and tasks.

    Without `since`, returns the current cursor only: call it before a full initial load,
    then pass the cursor as `since` to get everything that changed afterwards. Each item
    appears at most once, with its latest change; an `upsert` carries the current item and
    a `delete` carries `null`. Follow `cursor` while `has_more` is true.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "since",
                OpenApiTypes.INT,
                description="Cursor from a previous response. Omit to get the current cursor.",
            ),
            OpenApiParameter(
                "limit",
                OpenApiTypes.INT,
                description=f"Changes per page, default {DEFAULT_LIMIT}, max {MAX_LIMIT}.",
            ),
            OpenApiParameter(
                "types",
                OpenApiTypes.STR,
                description="Comma-separated subset of `categories,events,notes,tasks`.",
            ),
        ],
        responses=inline_serializer(
            "Sync",
            {
                "cursor": serializers.IntegerField(
                    help_text="`seq` of the last returned change (or `since` when there are "
                    "none); pass it as `since` next time."
                ),
                "has_more": serializers.BooleanField(),
                "changes": CHANGES_SCHEMA,
            },
        ),
    )
    def get(self, request):
        query = SyncQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        changes = Change.objects.filter(user=request.user)

        since = params.get("since")
        if since is None:
            cursor = changes.aggregate(cursor=Max("id"))["cursor"] or 0
            return Response({"cursor": cursor, "has_more": False, "changes": []})

        changes = changes.filter(id__gt=since).order_by("id")
        if params.get("types"):
            changes = changes.filter(type__in=params["types"])
        limit = params["limit"]
        rows = list(changes[: limit + 1])
        has_more = len(rows) > limit
        rows = rows[:limit]

        return Response(
            {
                "cursor": rows[-1].id if rows else since,
                "has_more": has_more,
                "changes": self._serialize(rows),
            }
        )

    def _serialize(self, rows):
        # One query per type for the items that still exist.
        wanted = {}
        for row in rows:
            if row.op == Change.Op.UPSERT:
                wanted.setdefault(row.type, []).append(row.object_id)
        items = {}
        for type, ids in wanted.items():
            resource = RESOURCES[type]
            objects = resource.queryset(self.request.user).filter(pk__in=ids)
            serializer = resource.serializer_class(
                objects, many=True, context={"request": self.request}
            )
            for data in serializer.data:
                items[type, data["id"]] = data

        result = []
        for row in rows:
            data = items.get((row.type, row.object_id)) if row.op == Change.Op.UPSERT else None
            result.append(
                {
                    "seq": row.id,
                    "type": row.type,
                    "id": row.object_id,
                    # An upsert whose object is gone without a delete row reads as deleted.
                    "op": Change.Op.UPSERT if data is not None else Change.Op.DELETE,
                    "data": data,
                }
            )
        return result
