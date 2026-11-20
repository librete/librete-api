from django.conf import settings
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import actions
from .models import PushSubscription
from .serializers import (
    PushSubscriptionInputSerializer,
    PushSubscriptionSerializer,
    VapidKeySerializer,
)

USER_AGENT_MAX_LENGTH = PushSubscription._meta.get_field("user_agent").max_length
INVALID_ACTION = _("This action link is invalid.")
GONE_ACTION = _("This action link has expired or was already used.")
ACTION_ERROR = inline_serializer("ActionError", {"detail": serializers.CharField()})


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


class ActionView(APIView):
    """Carry out a notification action (PWA push): mark a task done or snooze a reminder.

    The token in the URL is signed by the server, valid for 7 days and single-use, so no
    login is needed (the service worker calls it with a plain `fetch`). `done` marks the
    task finished (creating the next instance of a repeating task); `snooze` reminds again
    in the token's `minutes`. 204 on success; 400 for a malformed or tampered token, 410
    for an expired or already used one or a deleted item. Nothing changes on errors.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        auth=[],
        responses={
            204: None,
            400: OpenApiResponse(ACTION_ERROR, description="Malformed or tampered token."),
            410: OpenApiResponse(
                ACTION_ERROR, description="Expired or used token, or the item is gone."
            ),
        },
    )
    def get(self, request, token):
        try:
            actions.perform(token)
        except actions.ActionError as error:
            message = INVALID_ACTION if error.status == 400 else GONE_ACTION
            return Response({"detail": message}, status=error.status)
        return Response(status=status.HTTP_204_NO_CONTENT)
