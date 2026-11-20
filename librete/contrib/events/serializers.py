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

from .models import Event
from .recurrence import normalize_exdates


def _value(attrs, instance, name):
    return attrs[name] if name in attrs else getattr(instance, name, None)


class EventSerializer(DateRangeValidationMixin, OwnedModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all())
    reminders = RemindersField(
        required=False,
        help_text="Minutes before the start (0..40320, at most 5). Defaults to the user's "
        "`default_reminders` on create; `[]` means no reminders.",
    )
    recurrence = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=recurrence.MAX_LENGTH,
        help_text="RFC 5545 RRULE body without the `RRULE:` prefix, e.g. "
        "`FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2`, optionally with `COUNT=n` or "
        "`UNTIL=YYYYMMDDTHHMMSSZ`. FREQ is DAILY, WEEKLY, MONTHLY or YEARLY. Expanded from "
        '`start_date` in the author\'s time zone. Stored upper-cased; `null` (or `""`) = '
        "doesn't repeat.",
    )
    exdates = serializers.ListField(
        child=serializers.DateTimeField(),
        required=False,
        help_text="Original starts of skipped occurrences; returned in UTC, whole seconds, "
        "sorted and deduplicated.",
    )
    recurrence_parent = OwnedPrimaryKeyRelatedField(
        queryset=Event.objects.all(),
        required=False,
        allow_null=True,
        help_text="Set on an override: the recurring event (series) one occurrence of which "
        "this event replaces. Deleting the series deletes its overrides.",
    )
    original_start = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="Required with `recurrence_parent` (and only then): the original start of "
        "the replaced occurrence.",
    )
    occurrence_start = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        help_text="With `expand=1`: the original start of the occurrence (also set on "
        "overrides, to their `original_start`). Otherwise null.",
    )
    is_occurrence = serializers.BooleanField(
        read_only=True,
        help_text="True for virtual occurrences of a series in `expand=1` lists (`id` is the "
        "series id); false for stored events.",
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
            "recurrence",
            "exdates",
            "recurrence_parent",
            "original_start",
            "occurrence_start",
            "is_occurrence",
            "created_at",
            "updated_at",
            "version",
        )

    def _author(self):
        if self.instance is not None:
            return self.instance.author
        return self.context["request"].user

    def validate_exdates(self, value):
        try:
            return normalize_exdates(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "recurrence" in attrs:
            attrs["recurrence"] = (attrs["recurrence"] or "").strip().upper() or None
        rule = _value(attrs, self.instance, "recurrence")
        parent = _value(attrs, self.instance, "recurrence_parent")
        original_start = _value(attrs, self.instance, "original_start")

        if parent is not None:
            if self.instance is not None and parent.pk == self.instance.pk:
                raise serializers.ValidationError(
                    {"recurrence_parent": _("An event cannot replace its own occurrence.")}
                )
            if not parent.recurrence or parent.recurrence_parent_id is not None:
                raise serializers.ValidationError(
                    {"recurrence_parent": _("Choose a recurring event.")}
                )
            if rule:
                raise serializers.ValidationError(
                    {"recurrence": _("An event that replaces an occurrence cannot repeat.")}
                )
            if original_start is None:
                raise serializers.ValidationError(
                    {"original_start": _("This field is required with recurrence_parent.")}
                )
        elif original_start is not None:
            raise serializers.ValidationError(
                {"original_start": _("Only allowed together with recurrence_parent.")}
            )

        changed = self.instance is None or {"recurrence", "start_date"} & set(attrs)
        if rule and changed:
            start = _value(attrs, self.instance, "start_date")
            try:
                recurrence.normalize(rule, start, recurrence.zone(self._author().time_zone))
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"recurrence": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        if "reminders" not in validated_data:
            validated_data["reminders"] = list(validated_data["author"].default_reminders)
        return super().create(validated_data)
