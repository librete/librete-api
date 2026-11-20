from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import PushSubscription


class PushSubscriptionKeysSerializer(serializers.Serializer):
    p256dh = serializers.CharField(max_length=255)
    auth = serializers.CharField(max_length=255)


class PushSubscriptionInputSerializer(serializers.Serializer):
    """The browser's `PushSubscription.toJSON()`; other fields (expirationTime) are ignored."""

    endpoint = serializers.URLField(max_length=500)
    keys = PushSubscriptionKeysSerializer()

    def validate_endpoint(self, value):
        # The server POSTs to this URL; browsers' push services always use HTTPS.
        if not value.lower().startswith("https://"):
            raise serializers.ValidationError(_("The endpoint must be an HTTPS URL."))
        return value


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ("id", "endpoint", "created_at")
        read_only_fields = fields


class VapidKeySerializer(serializers.Serializer):
    public_key = serializers.CharField(
        allow_null=True, help_text="VAPID application server key; null when push is disabled."
    )
