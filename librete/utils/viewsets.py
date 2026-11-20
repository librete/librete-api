import functools
import re
import uuid

from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import ParseError
from rest_framework.response import Response

from .models import lock_owner

# `3`, `"3"` or `W/"3"`; `*` matches any version.
IF_MATCH_RE = re.compile(r'(?:W/)?"(\d+)"|(\d+)|(\*)')

CONFLICT_MESSAGE = _("This item was changed elsewhere.")


def _parse_uuid(value):
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def parse_if_match(request):
    """The version from the `If-Match` header, or None when absent (or `*`)."""
    header = request.headers.get("If-Match")
    if header is None:
        return None
    match = IF_MATCH_RE.fullmatch(header.strip())
    if match is None:
        raise ParseError(_("The If-Match header must hold a version number."))
    quoted, plain, _any = match.groups()
    if quoted is None and plain is None:
        return None
    return int(quoted or plain)


@functools.cache
def _conflict_serializer(serializer_class):
    name = serializer_class.__name__.removesuffix("Serializer")
    return inline_serializer(
        f"{name}Conflict",
        {"detail": serializers.CharField(), "current": serializer_class()},
    )


class OwnedModelSchema(AutoSchema):
    """Documents `If-Match`, the 409 conflict response and the idempotent-create 200."""

    def get_override_parameters(self):
        parameters = super().get_override_parameters()
        if self.method in ("PUT", "PATCH", "DELETE"):
            parameters.append(
                OpenApiParameter(
                    "If-Match",
                    OpenApiTypes.STR,
                    OpenApiParameter.HEADER,
                    description='The `version` the change is based on (`3`, `"3"` or '
                    '`W/"3"`). A different current version answers 409 and changes nothing.',
                )
            )
        return parameters

    def get_response_serializers(self):
        serializer = super().get_response_serializers()
        if self.method == "POST" and self._is_create_operation():
            return {201: serializer, 200: serializer}
        if self.method in ("PUT", "PATCH", "DELETE"):
            conflict = _conflict_serializer(serializer.__class__)
            ok = (204, None) if self.method == "DELETE" else (200, serializer)
            return {ok[0]: ok[1], 409: conflict}
        return serializer


class OwnedModelViewSet(viewsets.ModelViewSet):
    # CRUD restricted to the requesting user's own records (no docstring: it would become
    # the OpenAPI description of every subclass).
    # - Creates are idempotent: a POST whose `client_id` this user already used for this
    #   resource returns the existing item with 200 instead of creating a duplicate.
    # - PUT, PATCH and DELETE honour `If-Match: <version>`: a stale version answers 409 with
    #   the current item and changes nothing. Without the header the last write wins.
    # - Single-item responses carry `ETag: "<version>"`.

    model = None
    schema = OwnedModelSchema()

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    # Idempotent creates

    def _existing_for_client_id(self):
        data = self.request.data
        client_id = _parse_uuid(data.get("client_id") if hasattr(data, "get") else None)
        if client_id is None:
            return None
        return self.get_queryset().filter(client_id=client_id).first()

    def _existing_response(self, instance):
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        existing = self._existing_for_client_id()
        if existing is not None:
            return self._existing_response(existing)
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            # A concurrent request with the same client_id won the race.
            existing = self._existing_for_client_id()
            if existing is None:
                raise
            return self._existing_response(existing)

    # Optimistic concurrency

    def _conflict(self, instance):
        return Response(
            {"detail": CONFLICT_MESSAGE, "current": self.get_serializer(instance).data},
            status=status.HTTP_409_CONFLICT,
        )

    def _write_checked(self, write, request, *args, **kwargs):
        expected = parse_if_match(request)
        with transaction.atomic():
            # Serializes this user's writes, so nothing can change between check and write.
            lock_owner(request.user.pk)
            if expected is not None:
                instance = self.get_object()
                if instance.version != expected:
                    return self._conflict(instance)
            return write(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return self._write_checked(super().update, request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return self._write_checked(super().destroy, request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        data = getattr(response, "data", None)
        if (
            self.action in ("retrieve", "create", "update", "partial_update")
            and response.status_code in (200, 201)
            and isinstance(data, dict)
            and "version" in data
        ):
            response["ETag"] = f'"{data["version"]}"'
        return response
