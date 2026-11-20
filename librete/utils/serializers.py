from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class OwnedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """A primary key field that only accepts objects owned by the requesting user."""

    def get_queryset(self):
        request = self.context.get("request")
        queryset = super().get_queryset()
        if request is None or not request.user.is_authenticated:
            return queryset.none()
        return queryset.filter(author=request.user)


class DateRangeValidationMixin:
    """Validates that `end_date` is not before `start_date` (also on partial updates)."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": _("End date cannot be before start date.")}
            )
        return attrs


class OwnedModelSerializer(serializers.ModelSerializer):
    """Base serializer for `OwnedModel` resources.

    `client_id` can only be set on create; it is ignored on updates.
    """

    client_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Client-generated UUID that makes the create idempotent: a POST with a "
        "`client_id` already used for this resource returns the existing item (200). "
        "Ignored on updates.",
    )

    def update(self, instance, validated_data):
        validated_data.pop("client_id", None)
        return super().update(instance, validated_data)
