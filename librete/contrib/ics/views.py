import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponseNotModified
from django.utils.http import parse_etags
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView

from .feed import build_feed

# The feed is rebuilt at most this often per user (and calendar apps may cache it as long).
FEED_CACHE_SECONDS = 5 * 60
TOKEN_BYTES = 32


def feed_url(user):
    if not user.ics_token:
        return None
    return f"{settings.PUBLIC_URL}/ics/{user.ics_token}.ics"


class FeedSettingsSerializer(serializers.Serializer):
    url = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="The secret subscription URL (`/ics/<token>.ics`), or null without a feed.",
    )
    include_tasks = serializers.BooleanField(
        required=False, help_text="Include tasks with a date (as calendar events)."
    )


class FeedSettingsView(APIView):
    """The calendar (ICS) subscription feed of the requesting user.

    GET shows it; POST creates the secret URL or replaces it with a new one (the old URL
    stops working at once); PATCH changes `include_tasks` only; DELETE revokes the URL.
    """

    def _response(self, user):
        return Response({"url": feed_url(user), "include_tasks": user.ics_include_tasks})

    def _validated(self, request):
        serializer = FeedSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @extend_schema(responses=FeedSettingsSerializer)
    def get(self, request):
        return self._response(request.user)

    @extend_schema(request=FeedSettingsSerializer, responses=FeedSettingsSerializer)
    def post(self, request):
        data = self._validated(request)
        user = request.user
        user.ics_token = secrets.token_urlsafe(TOKEN_BYTES)
        user.ics_include_tasks = data.get("include_tasks", user.ics_include_tasks)
        user.save(update_fields=["ics_token", "ics_include_tasks"])
        return self._response(user)

    @extend_schema(request=FeedSettingsSerializer, responses=FeedSettingsSerializer)
    def patch(self, request):
        data = self._validated(request)
        user = request.user
        if "include_tasks" in data:
            user.ics_include_tasks = data["include_tasks"]
            user.save(update_fields=["ics_include_tasks"])
        return self._response(user)

    @extend_schema(responses={204: None})
    def delete(self, request):
        user = request.user
        user.ics_token = None
        user.save(update_fields=["ics_token"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class FeedTokenThrottle(SimpleRateThrottle):
    """Limits requests per feed URL (`THROTTLE_ICS_FEED`), whoever makes them."""

    scope = "ics_feed"

    def get_cache_key(self, request, view):
        token = view.kwargs.get("token", "")
        return self.cache_format % {
            "scope": self.scope,
            "ident": hashlib.sha256(token.encode()).hexdigest(),
        }


def cached_feed(user):
    """(ETag, body) of the user's feed, rebuilt at most every FEED_CACHE_SECONDS."""
    key = f"ics-feed:{user.pk}:{int(user.ics_include_tasks)}"
    cached = cache.get(key)
    if cached is None:
        body = build_feed(user, include_tasks=user.ics_include_tasks)
        cached = (f'"{hashlib.sha256(body).hexdigest()[:32]}"', body)
        cache.set(key, cached, FEED_CACHE_SECONDS)
    return cached


class FeedView(APIView):
    """The calendar feed (iCalendar) behind a secret URL, for calendar apps (no login).

    Events with their recurrence rules, skipped dates, changed occurrences and reminders
    (and, if enabled, tasks with a date). Cached for 5 minutes; supports `If-None-Match`.
    An unknown or revoked token gives 404.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, FeedTokenThrottle]

    def perform_content_negotiation(self, request, force=False):
        # Calendar apps ask for `text/calendar`, which no DRF renderer offers; the success
        # response is a plain HttpResponse anyway (errors fall back to JSON).
        return super().perform_content_negotiation(request, force=True)

    @extend_schema(
        auth=[],
        responses={
            (200, "text/calendar"): OpenApiResponse(OpenApiTypes.STR),
            304: None,
            404: None,
        },
    )
    def get(self, request, token):
        user = get_user_model().objects.filter(ics_token=token, is_active=True).first()
        if user is None:
            raise Http404
        etag, body = cached_feed(user)
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match:
            # Weak comparison (RFC 9110): W/"x" matches "x"; `*` matches any.
            tags = {tag.removeprefix("W/") for tag in parse_etags(if_none_match)}
            if "*" in tags or etag in tags:
                response = HttpResponseNotModified()
                response["ETag"] = etag
                response["Cache-Control"] = f"private, max-age={FEED_CACHE_SECONDS}"
                return response
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={FEED_CACHE_SECONDS}"
        response["Content-Disposition"] = 'inline; filename="librete.ics"'
        return response
