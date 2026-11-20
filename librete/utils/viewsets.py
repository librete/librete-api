import uuid

from django.db import IntegrityError, transaction
from rest_framework import status, viewsets
from rest_framework.response import Response


def _parse_uuid(value):
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


class OwnedModelViewSet(viewsets.ModelViewSet):
    """CRUD restricted to the requesting user's own records.

    Creates are idempotent: a POST whose `client_id` this user already used for this
    resource returns the existing item with 200 instead of creating a duplicate.
    """

    model = None

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

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
