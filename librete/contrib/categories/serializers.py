import re

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from librete.utils.serializers import OwnedModelSerializer

from .models import Category

COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")


class CategorySerializer(OwnedModelSerializer):
    color = serializers.CharField(
        required=False,
        allow_null=True,
        max_length=7,
        help_text="`#RRGGBB` (any case on input, returned in lower case) or null.",
    )
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
            "color",
            "events_count",
            "notes_count",
            "tasks_count",
            "created_at",
            "updated_at",
            "version",
        )

    def validate_color(self, value):
        if value is None:
            return None
        if not COLOR_RE.fullmatch(value):
            raise serializers.ValidationError(_("Enter a color in the #RRGGBB format."))
        return value.lower()
