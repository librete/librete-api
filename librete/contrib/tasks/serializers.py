from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from librete.contrib.categories.models import Category
from librete.contrib.reminders.fields import RemindersField
from librete.utils import recurrence
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
    reminders = RemindersField(
        required=False,
        help_text="Minutes before the due date (`end_date`, else `start_date`; none without "
        "a date or once finished), 0..40320, at most 5. Defaults to the user's "
        "`default_task_reminders` on create; `[]` means no reminders.",
    )
    repeat = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=recurrence.MAX_LENGTH,
        help_text="RRULE body like an event's `recurrence`, expanded from the due date "
        "(`end_date`, else `start_date`; one is required). Completing the task creates the "
        "next instance (its `repeat` has COUNT lowered by one). `null` = doesn't repeat.",
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
            "reminders",
            "repeat",
            "created_at",
            "updated_at",
            "version",
        )

    def _author(self):
        if self.instance is not None:
            return self.instance.author
        return self.context["request"].user

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "repeat" in attrs:
            attrs["repeat"] = (attrs["repeat"] or "").strip().upper() or None

        def value(name):
            return attrs[name] if name in attrs else getattr(self.instance, name, None)

        rule = value("repeat")
        changed = self.instance is None or {"repeat", "start_date", "end_date"} & set(attrs)
        if rule and changed:
            due = value("end_date") or value("start_date")
            if due is None:
                raise serializers.ValidationError(
                    {"repeat": _("A repeating task needs a due date or a start date.")}
                )
            try:
                recurrence.normalize(rule, due, recurrence.zone(self._author().time_zone))
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"repeat": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        if "reminders" not in validated_data:
            validated_data["reminders"] = list(validated_data["author"].default_task_reminders)
        return super().create(validated_data)

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
