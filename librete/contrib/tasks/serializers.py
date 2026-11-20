from rest_framework import serializers

from librete.contrib.categories.models import Category
from librete.utils.serializers import DateRangeValidationMixin, OwnedPrimaryKeyRelatedField

from .models import Task


class TaskSerializer(DateRangeValidationMixin, serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all())
    parent = OwnedPrimaryKeyRelatedField(
        queryset=Task.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Task
        fields = (
            "id",
            "name",
            "category",
            "parent",
            "start_date",
            "end_date",
            "description",
            "priority",
            "status",
            "created_at",
            "updated_at",
        )

    def validate_parent(self, parent):
        if parent is None or self.instance is None:
            return parent
        ancestor = parent
        while ancestor is not None:
            if ancestor.pk == self.instance.pk:
                raise serializers.ValidationError(
                    "A task cannot be its own parent or a subtask of its subtasks."
                )
            ancestor = ancestor.parent
        return parent
