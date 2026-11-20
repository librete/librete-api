from librete.contrib.categories.models import Category
from librete.contrib.reminders.fields import RemindersField
from librete.utils.serializers import (
    DateRangeValidationMixin,
    OwnedModelSerializer,
    OwnedPrimaryKeyRelatedField,
)

from .models import Event


class EventSerializer(DateRangeValidationMixin, OwnedModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all())
    reminders = RemindersField(
        required=False,
        help_text="Minutes before the start (0..40320, at most 5). Defaults to the user's "
        "`default_reminders` on create; `[]` means no reminders.",
    )

    class Meta:
        model = Event
        fields = (
            "id",
            "client_id",
            "name",
            "category",
            "start_date",
            "end_date",
            "location",
            "description",
            "reminders",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        if "reminders" not in validated_data:
            validated_data["reminders"] = list(validated_data["author"].default_reminders)
        return super().create(validated_data)
