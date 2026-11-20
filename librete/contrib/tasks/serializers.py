from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from librete.contrib.categories.models import Category
from librete.utils.serializers import (
    DateRangeValidationMixin,
    OwnedModelSerializer,
    OwnedPrimaryKeyRelatedField,
)

from .models import Task


class TaskSerializer(DateRangeValidationMixin, OwnedModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all())
    parent = OwnedPrimaryKeyRelatedField(
        queryset=Task.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Task
        fields = (
            "id",
            "client_id",
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
            "version",
        )

    def validate_parent(self, parent):
        if parent is None or self.instance is None:
            return parent
        ancestor = parent
        while ancestor is not None:
            if ancestor.pk == self.instance.pk:
                raise serializers.ValidationError(
                    _("A task cannot be its own parent or a subtask of its subtasks.")
                )
            ancestor = ancestor.parent
        return parent
