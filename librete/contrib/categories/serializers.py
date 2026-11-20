from rest_framework import serializers

from librete.utils.serializers import OwnedModelSerializer

from .models import Category


class CategorySerializer(OwnedModelSerializer):
    events_count = serializers.IntegerField(read_only=True)
    notes_count = serializers.IntegerField(read_only=True)
    tasks_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = (
            "id",
            "client_id",
            "name",
            "description",
            "events_count",
            "notes_count",
            "tasks_count",
            "created_at",
            "updated_at",
        )
