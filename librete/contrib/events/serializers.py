from rest_framework import serializers

from librete.contrib.categories.models import Category
from librete.utils.serializers import DateRangeValidationMixin, OwnedPrimaryKeyRelatedField

from .models import Event


class EventSerializer(DateRangeValidationMixin, serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all())

    class Meta:
        model = Event
        fields = (
            "id",
            "name",
            "category",
            "start_date",
            "end_date",
            "location",
            "description",
            "created_at",
            "updated_at",
        )
