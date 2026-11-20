from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from librete.contrib.reminders.fields import RemindersField

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    default_reminders = RemindersField(
        required=False,
        help_text="Minutes before the start used for new events (0..40320, at most 5).",
    )
    default_task_reminders = RemindersField(
        required=False,
        help_text="Minutes before the due date used for new tasks (0..40320, at most 5). "
        "Default `[]`.",
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "language",
            "time_zone",
            "default_reminders",
            "default_task_reminders",
            "date_joined",
        )
        read_only_fields = ("id", "email", "date_joined")


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError(_("Invalid password."))
        return value
