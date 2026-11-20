from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PushSubscription
from .serializers import (
    PushSubscriptionInputSerializer,
    PushSubscriptionSerializer,
    VapidKeySerializer,
)

USER_AGENT_MAX_LENGTH = PushSubscription._meta.get_field("user_agent").max_length


class VapidKeyView(APIView):
    """The VAPID public key the PWA subscribes with (`null` when push is not configured)."""

    @extend_schema(responses=VapidKeySerializer)
    def get(self, request):
        return Response({"public_key": settings.VAPID_PUBLIC_KEY or None})


class PushSubscriptionViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Web Push subscriptions of the requesting user's browsers (PWA reminders).

    POST takes the browser's PushSubscription JSON and creates the subscription, or
    updates the existing one with the same endpoint (201 / 200).
    """

    serializer_class = PushSubscriptionSerializer

    def get_queryset(self):
        return PushSubscription.objects.filter(user=self.request.user)

    @extend_schema(
        request=PushSubscriptionInputSerializer,
        responses={201: PushSubscriptionSerializer, 200: PushSubscriptionSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = PushSubscriptionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user_agent = request.headers.get("User-Agent", "")[:USER_AGENT_MAX_LENGTH]
        # An endpoint identifies one browser profile: if it was registered by another
        # account (someone signed out and in as another user), it moves to this user.
        subscription, created = PushSubscription.objects.update_or_create(
            endpoint=data["endpoint"],
            defaults={
                "user": request.user,
                "p256dh": data["keys"]["p256dh"],
                "auth": data["keys"]["auth"],
                "user_agent": user_agent,
            },
        )
        return Response(
            PushSubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
