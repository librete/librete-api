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
